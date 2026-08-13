import { shallowMount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import FinancialProfilePanel from "@/components/profile/FinancialProfilePanel.vue";

vi.mock("ant-design-vue", async (importOriginal) => {
  const original = await importOriginal<typeof import("ant-design-vue")>();
  return {
    ...original,
    message: {
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
        AModal: { template: "<div><slot /></div>" },
        ADrawer: { template: "<div><slot name='extra' /><slot /></div>" },
        AButton: { template: "<button><slot /></button>" },
        AEmpty: { template: "<div><slot /></div>" },
      },
    },
  });
}

describe("FinancialProfilePanel", () => {
  it("shows the front-end-only boundary and the profile skeleton", () => {
    const wrapper = mountPanel();

    expect(wrapper.text()).toContain("个人财务档案");
    expect(wrapper.text()).toContain("刷新后会重置");
    expect(wrapper.text()).toContain("申报年收入");
    expect(wrapper.text()).toContain("实时财务数据保持独立");
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

  it("updates the visible profile preview without persistence", () => {
    const wrapper = mountPanel();
    const setup = (
      wrapper.vm.$ as unknown as {
        setupState: {
          openProfileEditor: () => void;
          saveProfilePreview: () => void;
          profileForm: { birthDate: string; residenceCity: string };
          profile: { birthDate: string; residenceCity: string };
        };
      }
    ).setupState;

    setup.openProfileEditor();
    setup.profileForm.birthDate = "1990-05-06";
    setup.profileForm.residenceCity = "深圳市";
    setup.saveProfilePreview();

    expect(setup.profile.birthDate).toBe("1990-05-06");
    expect(setup.profile.residenceCity).toBe("深圳市");
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
