import axios from "axios";

import { http } from "@/services/http";
import type {
  PersonalFinancialProfile,
  PersonalFinancialProfileInput,
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
};
