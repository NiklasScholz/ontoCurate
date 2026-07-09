import createClient from "openapi-fetch";
import type { paths } from "./api";

export const client = createClient<paths>({
	baseUrl: import.meta.env.VITE_API_URL,
	credentials: "include",
});
