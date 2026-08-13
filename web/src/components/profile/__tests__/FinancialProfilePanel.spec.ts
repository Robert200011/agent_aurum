import { flushPromises, shallowMount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FinancialProfilePanel from "@/components/profile/FinancialProfilePanel.vue";
import { settingsApi } from "@/services/settings";
import type { PersonalFinancialProfile } from "@/types/api";

vi.mock("@/services/settings", () => ({
  settingsApi: {
    financialProfile: vi.fn(),
    createFinancialProfile: vi.fn(),
    updateFinancialProfile: vi.fn(),
  },
}));

vi.mock("ant-design-vue", async (importOriginal) => {
  const original = await importOriginal<typeof import("ant-design-vue")>();
  return {
    ...original,
    message: {
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn(),
    },
    Modal: {
      confirm: vi.fn(),
    },
  };
});

function mountPanel() {
  return shallowMount(FinancialProfilePanel, {
    global: {
      stubs: {
        AAlert: {
          props: ["message", "description"],
          template: "<div>{{ message }} {{ description }}</div>",
        },
        AProgress: true,
        ASpin: true,
        AModal: { template: "<div><slot /></div>" },
        ADrawer: { template: "<div><slot name='extra' /><slot /></div>" },
        AButton: { template: "<button><slot /></button>" },
        AEmpty: { template: "<div><slot /></div>" },
      },
    },
  });
}

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
  loadFinancialProfile: () => Promise<void>;
  saveFinancialProfile: () => Promise<void>;
  profileForm: {
    birthDate: string;
    residenceProvince: string;
    residenceCity: string;
    employmentStatus: string;
    occupation: string;
    annualIncome: string;
    annualExpenseBudget: string;
  };
  profile: { birthDate: string; residenceCity: string; occupation: string };
  profileExists: boolean;
  profileLoadFailed: boolean;
  profileSaving: boolean;
};

function stateOf(wrapper: ReturnType<typeof mountPanel>): PanelState {
  return (wrapper.vm.$ as unknown as { setupState: PanelState }).setupState;
}

describe("FinancialProfilePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(settingsApi.financialProfile).mockResolvedValue(null);
  });

  it("loads an empty persistent profile while keeping memory in preview", async () => {
    const wrapper = mountPanel();
    await flushPromises();

    expect(wrapper.text()).toContain("个人财务档案");
    expect(wrapper.text()).toContain("个人财务档案现已保存到后端数据库");
    expect(wrapper.text()).toContain("记忆功能仍为界面预览");
    expect(wrapper.text()).toContain("申报年收入");
    expect(wrapper.text()).toContain("实时财务数据保持独立");
    expect(settingsApi.financialProfile).toHaveBeenCalledOnce();
  });

  it("opens memory settings and reflects the preview switch state", () => {
    const wrapper = mountPanel();
    const setup = (
      wrapper.vm.$ as unknown as {
        setupState: {
          openMemorySettings: () => void;
          saveMemorySettings: () => void;
          memoryEnabledDraft: boolean;
          memoryEnabled: boolean;
          memorySettingsOpen: boolean;
        };
      }
    ).setupState;

    setup.openMemorySettings();
    expect(setup.memorySettingsOpen).toBe(true);

    setup.memoryEnabledDraft = false;
    setup.saveMemorySettings();

    expect(setup.memoryEnabled).toBe(false);
    expect(setup.memorySettingsOpen).toBe(false);
  });

  it("creates a missing profile and applies the server response", async () => {
    const wrapper = mountPanel();
    await flushPromises();
    const setup = stateOf(wrapper);
    vi.mocked(settingsApi.createFinancialProfile).mockResolvedValue(savedProfile);

    setup.openProfileEditor();
    setup.profileForm.birthDate = "1990-05-06";
    setup.profileForm.residenceProvince = " 广东省 ";
    setup.profileForm.residenceCity = "深圳市";
    setup.profileForm.employmentStatus = "employed";
    setup.profileForm.occupation = "产品经理";
    setup.profileForm.annualIncome = "300000";
    setup.profileForm.annualExpenseBudget = "120000";
    await setup.saveFinancialProfile();

    expect(settingsApi.createFinancialProfile).toHaveBeenCalledWith({
      birth_date: "1990-05-06",
      residence_province: "广东省",
      residence_city: "深圳市",
      employment_status: "employed",
      occupation: "产品经理",
      annual_income: "300000",
      annual_expense_budget: "120000",
      currency: "CNY",
    });
    expect(settingsApi.updateFinancialProfile).not.toHaveBeenCalled();
    expect(setup.profile.birthDate).toBe("1990-05-06");
    expect(setup.profile.residenceCity).toBe("深圳市");
    expect(setup.profileExists).toBe(true);
  });

  it("loads and updates an existing profile", async () => {
    vi.mocked(settingsApi.financialProfile).mockResolvedValue(savedProfile);
    const wrapper = mountPanel();
    await flushPromises();
    const setup = stateOf(wrapper);
    vi.mocked(settingsApi.updateFinancialProfile).mockResolvedValue({
      ...savedProfile,
      occupation: "高级产品经理",
    });

    expect(setup.profile.occupation).toBe("产品经理");
    setup.openProfileEditor();
    setup.profileForm.occupation = "高级产品经理";
    await setup.saveFinancialProfile();

    expect(settingsApi.updateFinancialProfile).toHaveBeenCalledOnce();
    expect(settingsApi.createFinancialProfile).not.toHaveBeenCalled();
    expect(setup.profile.occupation).toBe("高级产品经理");
  });

  it("keeps the editor open when saving fails", async () => {
    const wrapper = mountPanel();
    await flushPromises();
    const setup = stateOf(wrapper);
    vi.mocked(settingsApi.createFinancialProfile).mockRejectedValue(new Error("offline"));

    setup.openProfileEditor();
    await setup.saveFinancialProfile();

    expect(setup.profileExists).toBe(false);
    expect(setup.profileSaving).toBe(false);
  });

  it("supports retry after profile loading fails", async () => {
    vi.mocked(settingsApi.financialProfile)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(savedProfile);
    const wrapper = mountPanel();
    await flushPromises();
    const setup = stateOf(wrapper);

    expect(setup.profileLoadFailed).toBe(true);
    await setup.loadFinancialProfile();

    expect(setup.profileLoadFailed).toBe(false);
    expect(setup.profile.occupation).toBe("产品经理");
    expect(settingsApi.financialProfile).toHaveBeenCalledTimes(2);
  });

  it("adds a memory to the preview list", () => {
    const wrapper = mountPanel();
    const setup = (
      wrapper.vm.$ as unknown as {
        setupState: {
          openNewMemory: () => void;
          saveMemoryPreview: () => void;
          memoryForm: { title: string; content: string };
          memories: Array<{ title: string }>;
        };
      }
    ).setupState;
    const before = setup.memories.length;

    setup.openNewMemory();
    setup.memoryForm.title = "计划明年进修";
    setup.memoryForm.content = "预算规划需要预留明年的进修费用。";
    setup.saveMemoryPreview();

    expect(setup.memories).toHaveLength(before + 1);
    expect(setup.memories[0]?.title).toBe("计划明年进修");
  });
});
