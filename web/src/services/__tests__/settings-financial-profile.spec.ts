import { beforeEach, describe, expect, it, vi } from "vitest";

import { http } from "@/services/http";
import { settingsApi } from "@/services/settings";
import type {
  PersonalFinancialProfile,
  PersonalFinancialProfileInput,
} from "@/types/api";

vi.mock("@/services/http", () => ({
  http: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

const profile: PersonalFinancialProfile = {
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

const input: PersonalFinancialProfileInput = {
  birth_date: "1990-05-06",
  residence_province: "广东省",
  residence_city: "深圳市",
  employment_status: "employed",
  occupation: "产品经理",
  annual_income: "300000",
  annual_expense_budget: "120000",
  currency: "CNY",
};

describe("settings financial profile API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads an existing financial profile", async () => {
    vi.mocked(http.get).mockResolvedValue({ data: profile });

    await expect(settingsApi.financialProfile()).resolves.toEqual(profile);
    expect(http.get).toHaveBeenCalledWith("/users/me/financial-profile");
  });

  it("maps a 404 response to an empty profile", async () => {
    vi.mocked(http.get).mockRejectedValue({
      isAxiosError: true,
      response: { status: 404 },
    });

    await expect(settingsApi.financialProfile()).resolves.toBeNull();
  });

  it("creates and updates through the current-user endpoint", async () => {
    vi.mocked(http.post).mockResolvedValue({ data: profile });
    vi.mocked(http.patch).mockResolvedValue({ data: profile });

    await expect(settingsApi.createFinancialProfile(input)).resolves.toEqual(profile);
    await expect(settingsApi.updateFinancialProfile(input)).resolves.toEqual(profile);
    expect(http.post).toHaveBeenCalledWith("/users/me/financial-profile", input);
    expect(http.patch).toHaveBeenCalledWith("/users/me/financial-profile", input);
  });
});
