/*
 * Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *     http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/store/auth";

import App from "../App.vue";

const { getHealth, getTrusts, getSiteDetails } = vi.hoisted(() => ({
    getHealth: vi.fn(),
    getTrusts: vi.fn(),
    getSiteDetails: vi.fn()
}));

vi.mock("@/services/health-service", () => ({ getHealth }));
vi.mock("@/services/trust-service", () => ({ getTrusts }));
vi.mock("@/services/site-service", () => ({ getSiteDetails }));
vi.mock("@/utils/session-teardown", () => ({ replayPostSignOutNotice: vi.fn() }));

const mountApp = () => mount(App, {
    global: {
        stubs: {
            RouterView: true,
            AiRouteProgress: true,
            AiSnackbar: true
        }
    }
});

describe("App hub polling (FLIP#702)", () => {
    beforeEach(() => {
        setActivePinia(createPinia());
        getHealth.mockReset().mockResolvedValue([]);
        getTrusts.mockReset().mockResolvedValue([]);
        getSiteDetails.mockReset().mockResolvedValue({ banner: null });
    });

    it("calls no authenticated endpoint while signed out", async () => {
        const wrapper = mountApp();
        await flushPromises();

        expect(getHealth).not.toHaveBeenCalled();
        expect(getTrusts).not.toHaveBeenCalled();
        expect(getSiteDetails).not.toHaveBeenCalled();
        wrapper.unmount();
    });

    it("fetches once a user is signed in", async () => {
        const wrapper = mountApp();
        await flushPromises();
        expect(getTrusts).not.toHaveBeenCalled();

        useAuthStore().user = {
            username: "u",
            userId: "id",
            attributes: {
                sub: "id",
                email: "u@example.com"
            },
            permissions: []
        };
        await flushPromises();

        expect(getHealth).toHaveBeenCalledTimes(1);
        expect(getTrusts).toHaveBeenCalledTimes(1);
        expect(getSiteDetails).toHaveBeenCalledTimes(1);
        wrapper.unmount();
    });
});
