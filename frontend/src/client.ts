import createClient from "openapi-fetch";
import type { paths } from "./api";

export const client = createClient<paths>({
    baseUrl: import.meta.env.VITE_API_URL,
    credentials: "include",
});

client.use({
    onResponse({ response, schemaPath }) {
        if (response.status === 401 && !schemaPath.startsWith("/auth/")) {
            window.location.href = "/";
        }
        return response;
    },
});

export function apiUrl(path: string): string {
    return `${import.meta.env.VITE_API_URL}${path}`;
}

export function getErrorMessage(error: unknown, fallback: string): string {
	const detail = (error as { detail?: string | { msg: string }[] } | undefined)
		?.detail;
	if (Array.isArray(detail)) {
		return detail
			.map((d) => d.msg.replace(/^Value error, /i, ""))
			.join(", ");
	}
	return detail ?? fallback;
}
