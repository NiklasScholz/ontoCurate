import createClient from "openapi-fetch";
import type { paths } from "./api";

export const client = createClient<paths>({
	baseUrl: "http://localhost:8000",
	credentials: "include",
});
