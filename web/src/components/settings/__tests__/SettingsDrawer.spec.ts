import { createPinia, setActivePinia } from "pinia";
import { flushPromises, shallowMount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsDrawer from "@/components/settings/SettingsDrawer.vue";
import { financeApi } from "@/services/finance";
import { settingsApi } from "@/services/settings";
import type { User } from "@/types/api";

const accountList = {
  items: [
    {
      id: "account-id",
      name: "日常账户",
      account_type: "checking" as const,
      currency: "CNY",
      balance: "1200.0000",
      is_active: true,
      created_at: "2026-01-15T00:00:00Z",
      updated_at: "2026-01-15T00:00:00Z",
    },
  ],
  page: 1,
  page_size: 200,
  total: 1,
};

const profile = {
  display_name: null,
  created_at: "2026-01-15T00:00:00Z",
  updated_at: "2026-01-15T00:00:00Z",
};

const preferences = {
  default_account_id: null,
  base_currency: "CNY",
  timezone: "Asia/Shanghai",
  font_size: "medium" as const,
  layout_density: "comfortable" as const,
  hide_sensitive_amounts: false,
  created_at: "2026-01-15T00:00:00Z",
  updated_at: "2026-01-15T00:00:00Z",
};

vi.mock("@/services/finance", () => ({
  financeApi: {
    listAccounts: vi.fn(),
  },
}));

vi.mock("@/services/settings", () => ({
  settingsApi: {
    profile: vi.fn(),
    preferences: vi.fn(),
    updateProfile: vi.fn(),
    updatePreferences: vi.fn(),
  },
}));

const user: User = {
  id: "user-id",
  username: "user_test",
  email: "user@example.com",
  status: "active",
  password_changed_at: "2026-08-01T00:00:00Z",
  created_at: "2026-01-15T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

function mountDrawer() {
  return shallowMount(SettingsDrawer, {
    props: { open: true, user },
    global: {
      stubs: {
        ADrawer: { template: "<div><slot name='title' /><slot /></div>" },
        AAlert: {
          props: ["message", "description"],
          template:
            "<div class='alert-stub'>{{ message }} {{ description }}<slot name='action' /></div>",
        },
        AAvatar: { template: "<div><slot name='icon' /></div>" },
        AButton: { template: "<button><slot /></button>" },
      },
    },
  });
}

describe("SettingsDrawer", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
    vi.mocked(financeApi.listAccounts).mockResolvedValue(accountList);
    vi.mocked(settingsApi.profile).mockResolvedValue(profile);
    vi.mocked(settingsApi.preferences).mockResolvedValue(preferences);
  });

  it("shows current account information in the profile panel", () => {
    const wrapper = mountDrawer();

    expect(wrapper.text()).toContain("user_test");
    expect(wrapper.text()).toContain("user@example.com");
    expect(wrapper.get("#settings-panel-profile").isVisible()).toBe(true);
  });

  it("keeps only the selected settings module expanded", async () => {
    const wrapper = mountDrawer();
    const securityTrigger = wrapper.get(
      '[aria-controls="settings-panel-security"]',
    );

    await securityTrigger.trigger("click");

    expect(securityTrigger.attributes("aria-expanded")).toBe("true");
    expect(
      wrapper
        .get('[aria-controls="settings-panel-profile"]')
        .attributes("aria-expanded"),
    ).toBe("false");
    expect(wrapper.get("#settings-panel-profile").isVisible()).toBe(false);
    expect(wrapper.get("#settings-panel-security").isVisible()).toBe(true);
  });

  it("emits actions for password change and logout", async () => {
    const wrapper = mountDrawer();

    await wrapper
      .get('[aria-controls="settings-panel-security"]')
      .trigger("click");
    await wrapper.get("#settings-panel-security button").trigger("click");
    await wrapper.get(".logout-entry").trigger("click");

    expect(wrapper.emitted("changePassword")).toHaveLength(1);
    expect(wrapper.emitted("logout")).toHaveLength(1);
  });

  it("shows balances as sensitive content and opens full account management", async () => {
    const wrapper = mountDrawer();
    await flushPromises();

    await wrapper.get('[aria-controls="settings-panel-accounts"]').trigger("click");

    expect(wrapper.get("#settings-panel-accounts").isVisible()).toBe(true);
    expect(wrapper.get(".sensitive-amount").text()).toContain("1,200.00");
    await wrapper.get(".account-actions button").trigger("click");
    expect(wrapper.emitted("manageAccounts")).toHaveLength(1);
  });

  it("requires a separate confirmation flow for account deactivation", async () => {
    const wrapper = mountDrawer();

    await wrapper
      .get('[aria-controls="settings-panel-deactivation"]')
      .trigger("click");

    expect(wrapper.get("#settings-panel-deactivation").isVisible()).toBe(true);
    expect(wrapper.get("#settings-panel-deactivation").text()).toContain(
      "财务与知识库数据不会在此步骤中被物理删除",
    );
    await wrapper.get(".deactivation-request").trigger("click");
    expect(wrapper.emitted("requestAccountDeactivation")).toHaveLength(1);
  });

  it("shows recoverable errors for settings and account loading", async () => {
    vi.mocked(settingsApi.profile).mockRejectedValueOnce(new Error("offline"));
    vi.mocked(financeApi.listAccounts).mockRejectedValueOnce(new Error("offline"));
    const wrapper = mountDrawer();
    await flushPromises();

    expect(wrapper.text()).toContain("设置资料加载失败");
    await wrapper.get('[aria-controls="settings-panel-accounts"]').trigger("click");
    expect(wrapper.get("#settings-panel-accounts").text()).toContain(
      "账户列表加载失败",
    );

    await wrapper.get(".settings-feedback button").trigger("click");
    await wrapper.get("#settings-panel-accounts button").trigger("click");
    await flushPromises();

    expect(settingsApi.profile).toHaveBeenCalledTimes(2);
    expect(financeApi.listAccounts).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).not.toContain("设置资料加载失败");
    expect(wrapper.get("#settings-panel-accounts").text()).toContain("日常账户");
  });
});
