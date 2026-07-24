"""现金流交易的增删改查、搜索和表格导入接口。"""

# 路由处理器负责校验传输层输入，服务层负责维护账本不变量。
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, File, Query, Response, UploadFile, status

from app.api.dependencies import FinanceServiceDependency
from app.api.schemas.finance import (
    ImportErrorItem,
    TransactionCreate,
    TransactionImportResponse,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdate,
)
from app.finance.importers.tabular import MAX_IMPORT_BYTES, parse_transaction_file
from app.finance.types import TransactionType

# 构造已认证服务时会注入经过验证的租户身份。
# 交易类型是有限的查询枚举，而不是任意过滤文本。
# API 不在路由、查询参数或请求体中接受用户标识符。
router = APIRouter(prefix="/finance/transactions", tags=["finance-transactions"])


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    service: FinanceServiceDependency,
) -> TransactionResponse:
    """记录现金流，并由服务原子更新对应账户。"""

    # 服务将交易记录创建与带方向的账户余额变更绑定在同一事务中。
    transaction = await service.create_transaction(**payload.model_dump())
    return TransactionResponse.model_validate(transaction)


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    service: FinanceServiceDependency,
    account_id: UUID | None = None,
    transaction_type: TransactionType | None = None,
    category: str | None = Query(default=None, min_length=1, max_length=128),
    start_date: date | None = None,
    end_date: date | None = None,
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    search: str | None = Query(default=None, min_length=1, max_length=256),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> TransactionListResponse:
    """使用有界过滤条件和分页搜索当前租户的交易。"""

    # 币种标准化使等值过滤条件能够继续使用索引。
    result = await service.list_transactions(
        account_id=account_id,
        transaction_type=transaction_type,
        category=category,
        start_date=start_date,
        end_date=end_date,
        currency=currency.upper() if currency else None,
        search=search,
        page=page,
        page_size=page_size,
    )
    # 分页元数据与明细查询使用同一组过滤条件。
    # 导入指纹和归属标识符不会进入公开接口契约。
    return TransactionListResponse(
        items=[TransactionResponse.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


# 上传处理与普通 JSON 创建接口分离，使文件限制和
# 部分导入策略在 HTTP 边界保持明确。
@router.post("/import", response_model=TransactionImportResponse)
async def import_transactions(
    service: FinanceServiceDependency,
    account_id: UUID,
    strict: bool = True,
    file: UploadFile = File(...),
) -> TransactionImportResponse:
    """解析一个受大小限制的上传文件，并返回逐行导入结果。"""

    # 比上限多读取一个字节即可识别超大输入，
    # 同时避免在应用内存中缓存无界请求体。
    content = await file.read(MAX_IMPORT_BYTES + 1)
    # 解析过程不执行公式、限制行数，并且与模型执行完全无关。
    rows = parse_transaction_file(file.filename or "upload", content)
    result = await service.import_transactions(
        account_id=account_id,
        rows=rows,
        strict=strict,
    )
    # 校验错误按源文件行返回，不暴露原始异常数据。
    return TransactionImportResponse(
        total_rows=result.total_rows,
        imported_rows=result.imported_rows,
        skipped_rows=result.skipped_rows,
        errors=[
            ImportErrorItem(row=item.row, field=item.field, message=item.message)
            for item in result.errors
        ],
        committed=result.committed,
    )


# 详情路由先完成 UUID 解析，再由服务执行租户查询。
# 不提供任何可绕过仓储归属过滤的后备路径。
@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    service: FinanceServiceDependency,
) -> TransactionResponse:
    """返回一笔交易，且不接受客户端提供的用户标识符。"""

    # 显式归属过滤让跨租户标识符与不存在的标识符表现一致。
    return TransactionResponse.model_validate(await service.get_transaction(transaction_id))


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: UUID,
    payload: TransactionUpdate,
    service: FinanceServiceDependency,
) -> TransactionResponse:
    """应用交易修正，并保留可空文本字段是否被省略的信息。"""

    # `None` 既可能表示“清空描述”，也可能表示“未提供字段”。
    # 额外传递字段存在标记可保持 PATCH 语义明确。
    transaction = await service.update_transaction(
        transaction_id,
        **payload.model_dump(),
        # 字段存在性用于区分省略与主动传入空值清除。
        description_provided="description" in payload.model_fields_set,
    )
    # 服务提交交易记录和余额后才执行序列化。
    return TransactionResponse.model_validate(transaction)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: UUID,
    service: FinanceServiceDependency,
) -> Response:
    """删除现金流记录，并冲销其对账户余额的影响。"""

    # 冲销提交后返回 204，不携带可能过期的资源表示。
    # 服务删除交易前会先反向应用其原始现金影响。
    await service.delete_transaction(transaction_id)
    # 空响应确保不会返回删除前的旧余额。
    return Response(status_code=status.HTTP_204_NO_CONTENT)
