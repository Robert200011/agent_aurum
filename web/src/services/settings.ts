import axios from "axios";

import { http } from "@/services/http";
import type {
  PersonalFinancialProfile,
  PersonalFinancialProfileInput,
  MemorySettings,
  MemorySettingsUpdate,
  UserMemory,
  UserMemoryInput,
  UserMemoryList,
  UserMemoryUpdate,
  UserPreferences,
  UserPreferenceUpdate,
  UserProfile,
} from "@/types/api";

export const settingsApi = {
  async profile(): Promise<UserProfile> {
    const response = await http.get<UserProfile>("/users/me/profile");
    return response.data;
  },
  async updateProfile(displayName: string | null): Promise<UserProfile> {
    const response = await http.patch<UserProfile>("/users/me/profile", {
      display_name: displayName,
    });
    return response.data;
  },
  async preferences(): Promise<UserPreferences> {
    const response = await http.get<UserPreferences>("/users/me/preferences");
    return response.data;
  },
  async updatePreferences(
    values: UserPreferenceUpdate,
  ): Promise<UserPreferences> {
    const response = await http.patch<UserPreferences>(
      "/users/me/preferences",
      values,
    );
    return response.data;
  },
  async financialProfile(): Promise<PersonalFinancialProfile | null> {
    try {
      const response = await http.get<PersonalFinancialProfile>(
        "/users/me/financial-profile",
      );
      return response.data;
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) return null;
      throw error;
    }
  },
  async createFinancialProfile(
    values: PersonalFinancialProfileInput,
  ): Promise<PersonalFinancialProfile> {
    const response = await http.post<PersonalFinancialProfile>(
      "/users/me/financial-profile",
      values,
    );
    return response.data;
  },
  async updateFinancialProfile(
    values: PersonalFinancialProfileInput,
  ): Promise<PersonalFinancialProfile> {
    const response = await http.patch<PersonalFinancialProfile>(
      "/users/me/financial-profile",
      values,
    );
    return response.data;
  },
  async memorySettings(): Promise<MemorySettings> {
    const response = await http.get<MemorySettings>("/users/me/memory-settings");
    return response.data;
  },
  async updateMemorySettings(values: MemorySettingsUpdate): Promise<MemorySettings> {
    const response = await http.patch<MemorySettings>(
      "/users/me/memory-settings",
      values,
    );
    return response.data;
  },
  async memories(page = 1, pageSize = 50): Promise<UserMemoryList> {
    const response = await http.get<UserMemoryList>("/users/me/memories", {
      params: { page, page_size: pageSize },
    });
    return response.data;
  },
  async createMemory(values: UserMemoryInput, idempotencyKey: string): Promise<UserMemory> {
    const response = await http.post<UserMemory>("/users/me/memories", values, {
      headers: { "Idempotency-Key": idempotencyKey },
    });
    return response.data;
  },
  async updateMemory(memoryId: string, values: UserMemoryUpdate): Promise<UserMemory> {
    const response = await http.patch<UserMemory>(
      `/users/me/memories/${memoryId}`,
      values,
    );
    return response.data;
  },
  async deleteMemory(memoryId: string): Promise<void> {
    await http.delete(`/users/me/memories/${memoryId}`);
  },
};
