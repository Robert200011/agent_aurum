import { shallowMount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppShell from "@/layouts/AppShell.vue";

const replace = vi.fn();
const logout = vi.fn();
const deactivateAccount = vi.fn();

vi.mock("vue-router", () => ({
  useRoute: () => ({ path: "/", meta: { title: "财务总览" } }),
  useRouter: () => ({ push: vi.fn(), replace }),
}));

vi.mock("@/stores/auth", () => ({
  useAuthStore: () => ({
    user: { username: "user_test" },
    logout,
    deactivateAccount,
  }),
}));

vi.mock("@/stores/settings", () => ({
  useSettingsStore: () => ({
    displayName: null,
    initialize: vi.fn().mockResolvedValue(undefined),
  }),
}));

describe("AppShell logout confirmation", () => {
  beforeEach(() => {
    replace.mockReset();
    logout.mockReset();
    logout.mockResolvedValue(undefined);
    deactivateAccount.mockReset();
    deactivateAccount.mockResolvedValue(undefined);
  });

  it("waits for confirmation before logging out", async () => {
    const wrapper = shallowMount(AppShell, {
      global: {
        stubs: {
          RouterView: {
            template: '<div><slot :Component="null" /></div>',
          },
        },
      },
    });
    const setup = (
      wrapper.vm.$ as unknown as {
        setupState: {
          requestLogout: () => void;
          confirmLogout: () => Promise<void>;
          logoutConfirmOpen: boolean;
        };
      }
    ).setupState;

    setup.requestLogout();

    expect(setup.logoutConfirmOpen).toBe(true);
    expect(logout).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();

    await setup.confirmLogout();

    expect(logout).toHaveBeenCalledOnce();
    expect(replace).toHaveBeenCalledWith("/login");
  });

  it("opens and closes the embedded agent from the sidebar button", async () => {
    const wrapper = shallowMount(AppShell, {
      global: {
        stubs: {
          RouterView: {
            template: '<div><slot :Component="null" /></div>',
          },
          ChatView: true,
        },
      },
    });
    const launcher = wrapper.get(".assistant-entry");

    expect(launcher.attributes("aria-expanded")).toBe("false");

    await launcher.trigger("click");

    expect(launcher.attributes("aria-expanded")).toBe("true");
    expect(wrapper.find(".agent-drawer").isVisible()).toBe(true);

    await wrapper.get(".agent-drawer-header button").trigger("click");

    expect(launcher.attributes("aria-expanded")).toBe("false");
  });

  it("opens the same embedded agent from the header star button", async () => {
    const wrapper = shallowMount(AppShell, {
      global: {
        stubs: {
          RouterView: {
            template: '<div><slot :Component="null" /></div>',
          },
          ChatView: true,
        },
      },
    });
    const headerLauncher = wrapper.get(".header-agent-entry");

    expect(headerLauncher.attributes("aria-expanded")).toBe("false");

    await headerLauncher.trigger("click");

    expect(headerLauncher.attributes("aria-expanded")).toBe("true");
    expect(wrapper.get(".assistant-entry").attributes("aria-expanded")).toBe(
      "true",
    );
    expect(wrapper.get(".app-layout").classes()).toContain("agent-is-open");
    expect(wrapper.find(".agent-drawer").isVisible()).toBe(true);
  });

  it("opens an independent settings center from the gear button", async () => {
    const wrapper = shallowMount(AppShell, {
      global: {
        stubs: {
          RouterView: {
            template: '<div><slot :Component="null" /></div>',
          },
          ChatView: true,
        },
      },
    });

    const settingsTrigger = wrapper.get(".settings-trigger");

    expect(settingsTrigger.attributes("aria-label")).toBe("打开设置中心");
    expect(settingsTrigger.attributes("aria-expanded")).toBe("false");

    await settingsTrigger.trigger("click");

    expect(settingsTrigger.attributes("aria-expanded")).toBe("true");
    expect(wrapper.get(".user-trigger").element.tagName).toBe("DIV");
    expect(wrapper.get(".header-actions").text()).toContain("user_test");
  });

  it("enables account deactivation only after all confirmations match", async () => {
    const wrapper = shallowMount(AppShell, {
      global: {
        stubs: {
          RouterView: { template: '<div><slot :Component="null" /></div>' },
          ChatView: true,
        },
      },
    });
    const setup = (
      wrapper.vm.$ as unknown as {
        setupState: {
          requestAccountDeactivation: () => void;
          confirmAccountDeactivation: () => Promise<void>;
          deactivationForm: {
            acknowledged: boolean;
            username: string;
            currentPassword: string;
          };
          canDeactivateAccount: boolean;
        };
      }
    ).setupState;

    setup.requestAccountDeactivation();
    expect(setup.canDeactivateAccount).toBe(false);

    setup.deactivationForm.acknowledged = true;
    setup.deactivationForm.username = "user_test";
    setup.deactivationForm.currentPassword = "test-password";
    expect(setup.canDeactivateAccount).toBe(true);

    await setup.confirmAccountDeactivation();
    expect(deactivateAccount).toHaveBeenCalledWith("user_test", "test-password");
    expect(replace).toHaveBeenCalledWith({
      path: "/login",
      query: { deactivated: "1" },
    });
  });

  it("does not open the agent shortcut while the user is typing", () => {
    const wrapper = shallowMount(AppShell, {
      global: {
        stubs: {
          RouterView: { template: '<div><slot :Component="null" /></div>' },
          ChatView: true,
        },
      },
    });
    const setup = (
      wrapper.vm.$ as unknown as {
        setupState: {
          handleGlobalKeydown: (event: KeyboardEvent) => void;
          agentOpen: boolean;
        };
      }
    ).setupState;
    const input = document.createElement("input");
    const event = new KeyboardEvent("keydown", { key: "/", ctrlKey: true });
    Object.defineProperty(event, "target", { value: input });

    setup.handleGlobalKeydown(event);

    expect(setup.agentOpen).toBe(false);
  });

  it("prevents duplicate account deactivation submissions", async () => {
    let finishRequest: (() => void) | undefined;
    deactivateAccount.mockReturnValue(
      new Promise<void>((resolve) => {
        finishRequest = resolve;
      }),
    );
    const wrapper = shallowMount(AppShell, {
      global: {
        stubs: {
          RouterView: { template: '<div><slot :Component="null" /></div>' },
          ChatView: true,
        },
      },
    });
    const setup = (
      wrapper.vm.$ as unknown as {
        setupState: {
          confirmAccountDeactivation: () => Promise<void>;
          deactivationForm: {
            acknowledged: boolean;
            username: string;
            currentPassword: string;
          };
        };
      }
    ).setupState;
    setup.deactivationForm.acknowledged = true;
    setup.deactivationForm.username = "user_test";
    setup.deactivationForm.currentPassword = "test-password";

    const firstRequest = setup.confirmAccountDeactivation();
    await setup.confirmAccountDeactivation();

    expect(deactivateAccount).toHaveBeenCalledOnce();
    finishRequest?.();
    await firstRequest;
  });
});
