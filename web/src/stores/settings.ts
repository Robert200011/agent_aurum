import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { settingsApi } from "@/services/settings";
import type {
  UserPreferences,
  UserPreferenceUpdate,
  UserProfile,
} from "@/types/api";

const DEFAULT_PROFILE: UserProfile = {
  display_name: null,
  created_at: "",
  updated_at: "",
};

const DEFAULT_PREFERENCES: UserPreferences = {
  default_account_id: null,
  base_currency: "CNY",
  timezone: "Asia/Shanghai",
  font_size: "medium",
  layout_density: "comfortable",
  hide_sensitive_amounts: false,
  created_at: "",
  updated_at: "",
};

function applyPreferences(preferences: UserPreferences): void {
  const root = document.documentElement;
  root.dataset.fontSize = preferences.font_size;
  root.dataset.layoutDensity = preferences.layout_density;
  root.dataset.hideSensitiveAmounts = String(
    preferences.hide_sensitive_amounts,
  );
}

export const useSettingsStore = defineStore("settings", () => {
  const profile = ref<UserProfile>({ ...DEFAULT_PROFILE });
  const preferences = ref<UserPreferences>({ ...DEFAULT_PREFERENCES });
  const initialized = ref(false);
  const loading = ref(false);
  const savingProfile = ref(false);
  const savingPreferences = ref(false);
  const loadFailed = ref(false);
  let initializePromise: Promise<void> | null = null;

  const displayName = computed(() => profile.value.display_name);

  async function initialize(): Promise<void> {
    if (initialized.value) return;
    if (initializePromise) return initializePromise;

    loading.value = true;
    loadFailed.value = false;
    initializePromise = Promise.all([
      settingsApi.profile(),
      settingsApi.preferences(),
    ])
      .then(([nextProfile, nextPreferences]) => {
        profile.value = nextProfile;
        preferences.value = nextPreferences;
        applyPreferences(nextPreferences);
        initialized.value = true;
      })
      .catch(() => {
        loadFailed.value = true;
        applyPreferences(preferences.value);
      })
      .finally(() => {
        loading.value = false;
        initializePromise = null;
      });

    return initializePromise;
  }

  async function updateProfile(displayNameValue: string | null): Promise<void> {
    savingProfile.value = true;
    try {
      profile.value = await settingsApi.updateProfile(displayNameValue);
    } finally {
      savingProfile.value = false;
    }
  }

  async function updatePreferences(
    values: UserPreferenceUpdate,
  ): Promise<void> {
    savingPreferences.value = true;
    try {
      preferences.value = await settingsApi.updatePreferences(values);
      applyPreferences(preferences.value);
    } finally {
      savingPreferences.value = false;
    }
  }

  async function refreshPreferences(): Promise<void> {
    preferences.value = await settingsApi.preferences();
    applyPreferences(preferences.value);
  }

  function reset(): void {
    profile.value = { ...DEFAULT_PROFILE };
    preferences.value = { ...DEFAULT_PREFERENCES };
    initialized.value = false;
    loadFailed.value = false;
    applyPreferences(preferences.value);
  }

  return {
    profile,
    preferences,
    displayName,
    initialized,
    loading,
    savingProfile,
    savingPreferences,
    loadFailed,
    initialize,
    updateProfile,
    updatePreferences,
    refreshPreferences,
    reset,
  };
});
