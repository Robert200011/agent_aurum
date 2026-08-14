import { flushPromises, shallowMount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FinancialProfilePanel from "@/components/profile/FinancialProfilePanel.vue";
import { settingsApi } from "@/services/settings";
import type { MemorySettings, PersonalFinancialProfile, UserMemory } from "@/types/api";

vi.mock("@/services/settings", () => ({
  settingsApi: {
    financialProfile: vi.fn(),
    createFinancialProfile: vi.fn(),
    updateFinancialProfile: vi.fn(),
    memorySettings: vi.fn(),
    updateMemorySettings: vi.fn(),
    memories: vi.fn(),
    createMemory: vi.fn(),
    updateMemory: vi.fn(),
    deleteMemory: vi.fn(),
  },
}));

vi.mock("ant-design-vue", async (importOriginal) => {
  const original = await importOriginal<typeof import("ant-design-vue")>();
  return {
    ...original,
    message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
    Modal: { confirm: vi.fn() },
  };
});

function mountPanel() {
  return shallowMount(FinancialProfilePanel, {
    global: {
      stubs: {
        AAlert: { props: ["message", "description"], template: "<div>{{ message }} {{ description }}</div>" },
        AProgress: true,
        ASpin: true,
        APagination: true,
        AModal: { template: "<div><slot /></div>" },
        ADrawer: { template: "<div><slot name='extra' /><slot /></div>" },
        AButton: { template: "<button><slot /></button>" },
        AEmpty: { template: "<div><slot /></div>" },
      },
    },
  });
}

const settings: MemorySettings = {
  memory_enabled: true,
  chat_save_enabled: true,
  answer_recall_enabled: true,
  created_at: "2026-08-13T00:00:00Z",
  updated_at: "2026-08-13T00:00:00Z",
};

const memory: UserMemory = {
  id: "memory-id",
  category: "goal",
  title: "建立应急储备",
  content: "先建立覆盖六个月必要支出的应急储备。",
  status: "active",
  source_type: "manual_ui",
  created_at: "2026-08-13T00:00:00Z",
  updated_at: "2026-08-13T00:00:00Z",
};

const savedProfile: PersonalFinancialProfile = {
  id: "profile-id",
  birth_date: "1990-05-06",
  residence_province: "广东省",
  residence_city: "深圳市",
  employment_status: "employed",
  occupation: "产品经理",
  annual_income: "300000.0000",
  annual_expense_budget: "120000.0000",
  currency: "CNY",
  created_at: "2026-08-13T00:00:00Z",
  updated_at: "2026-08-13T00:00:00Z",
};

type PanelState = {
  openProfileEditor: () => void;
  saveFinancialProfile: () => Promise<void>;
  openNewMemory: () => void;
  saveMemory: () => Promise<void>;
  saveMemorySettings: () => Promise<void>;
  toggleMemoryStatus: (memory: UserMemory) => Promise<void>;
  profileForm: Record<string, string>;
  memoryForm: { category: "goal"; title: string; content: string };
  profile: { occupation: string };
  profileExists: boolean;
  memoryEnabledDraft: boolean;
  memoryEnabled: boolean;
  memories: UserMemory[];
};

function stateOf(wrapper: ReturnType<typeof mountPanel>): PanelState {
  return (wrapper.vm.$ as unknown as { setupState: PanelState }).setupState;
}

describe("FinancialProfilePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(settingsApi.financialProfile).mockResolvedValue(null);
    vi.mocked(settingsApi.memorySettings).mockResolvedValue(settings);
    vi.mocked(settingsApi.memories).mockResolvedValue({ items: [memory], total: 1, page: 1, page_size: 20 });
  });

  it("loads the persistent profile, memory settings, and memory list", async () => {
    const wrapper = mountPanel();
    await flushPromises();

    expect(wrapper.text()).toContain("个人档案与长期记忆已持久化");
    expect(wrapper.text()).toContain("建立应急储备");
    expect(settingsApi.financialProfile).toHaveBeenCalledOnce();
    expect(settingsApi.memorySettings).toHaveBeenCalledOnce();
    expect(settingsApi.memories).toHaveBeenCalledWith(1, 20);
  });

  it("persists the memory master switch", async () => {
    const wrapper = mountPanel();
    await flushPromises();
    const setup = stateOf(wrapper);
    vi.mocked(settingsApi.updateMemorySettings).mockResolvedValue({ ...settings, memory_enabled: false });

    setup.memoryEnabledDraft = false;
    await setup.saveMemorySettings();

    expect(settingsApi.updateMemorySettings).toHaveBeenCalledWith({ memory_enabled: false });
    expect(setup.memoryEnabled).toBe(false);
  });

  it("creates a manual memory through the API", async () => {
    const wrapper = mountPanel();
    await flushPromises();
    const setup = stateOf(wrapper);
    const created = { ...memory, id: "new-memory", title: "计划明年进修", content: "预留进修费用。" };
    vi.mocked(settingsApi.createMemory).mockResolvedValue(created);

    setup.openNewMemory();
    setup.memoryForm.title = created.title;
    setup.memoryForm.content = created.content;
    await setup.saveMemory();

    expect(settingsApi.createMemory).toHaveBeenCalledWith(
      { category: "goal", title: created.title, content: created.content },
      expect.any(String),
    );
    expect(setup.memories[0]?.id).toBe("new-memory");
  });

  it("disables an existing memory through the API", async () => {
    const wrapper = mountPanel();
    await flushPromises();
    const setup = stateOf(wrapper);
    vi.mocked(settingsApi.updateMemory).mockResolvedValue({ ...memory, status: "disabled" });

    await setup.toggleMemoryStatus(memory);

    expect(settingsApi.updateMemory).toHaveBeenCalledWith(memory.id, { status: "disabled" });
    expect(setup.memories[0]?.status).toBe("disabled");
  });

  it("creates and updates the persistent financial profile", async () => {
    const wrapper = mountPanel();
    await flushPromises();
    const setup = stateOf(wrapper);
    vi.mocked(settingsApi.createFinancialProfile).mockResolvedValue(savedProfile);
    setup.openProfileEditor();
    Object.assign(setup.profileForm, {
      birthDate: "1990-05-06",
      residenceProvince: "广东省",
      residenceCity: "深圳市",
      employmentStatus: "employed",
      occupation: "产品经理",
      annualIncome: "300000",
      annualExpenseBudget: "120000",
    });

    await setup.saveFinancialProfile();

    expect(settingsApi.createFinancialProfile).toHaveBeenCalledOnce();
    expect(setup.profileExists).toBe(true);
    expect(setup.profile.occupation).toBe("产品经理");
  });
});
