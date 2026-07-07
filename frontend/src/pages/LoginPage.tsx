import { useState, type ChangeEvent } from "react";
import { MailIcon, LockKeyholeIcon, UserIcon, TriangleAlertIcon } from "lucide-react";
import Root from "../components/Root";
import { client } from "../client";
import { useNavigate } from "react-router-dom";
import { GoogleLogin } from "@react-oauth/google";
import { useAuth } from "../context/useAuth";

export default function LoginPage() {
    const [isRegister, setIsRegister] = useState(false);
    const [formData, setFormData] = useState({ username: "", login_name: "", password: "" });
    const [error, setError] = useState<string | null>(null);

    const navigate = useNavigate();
    const { refreshUser } = useAuth();

    const onChange = (e: ChangeEvent<HTMLInputElement>) => {
        setFormData((prev) => ({ ...prev, [e.target.name]: e.target.value }));
    };

    const handleSubmit = async () => {
        setError(null);
        const endpoint = isRegister ? "/auth/register" : "/auth/login";
        const body = isRegister
            ? { username: formData.username, email: formData.login_name, password: formData.password }
            : { login_name: formData.login_name, password: formData.password };
        const { error } = await client.POST(endpoint, { body: body as never });
        if (error) {
            const detail = (error as { detail?: string | { msg: string }[] }).detail;
            if (Array.isArray(detail)) {
                setError(detail.map((d) => d.msg.replace(/^Value error, /i, "")).join(", "));
            } else {
                setError(detail ?? "Something went wrong");
            }
            return;
        }
        await refreshUser();
        navigate("/workspaces");
    };

    return (
        <Root className="min-h-screen">
            <div className="flex flex-col w-full max-w-md mx-auto p-8 rounded-2xl shadow-xl" style={{ background: "#ffffff" }}>
                <div className="flex flex-row gap-3 pb-4">
                    <h1 className="text-3xl font-bold my-auto" style={{ color: "#4B5563" }}>OntoCurate - {isRegister ? "Register" : "Login"}</h1>
                </div>
                

                <div className="flex flex-col gap-4">
                    {isRegister && (
                        <div>
                            <label className="block mb-2 text-sm font-medium" style={{ color: "#111827" }}>Username</label>
                            <div className="relative text-gray-400">
                                <span className="absolute inset-y-0 left-0 flex items-center pl-3">
                                    <UserIcon size={20} />
                                </span>
                                <input
                                    type="text"
                                    name="username"
                                    value={formData.username}
                                    onChange={onChange}
                                    placeholder="Username"
                                    className="pl-11 bg-gray-50 text-gray-600 border border-gray-300 sm:text-sm rounded-lg focus:ring-1 focus:ring-gray-400 focus:border-transparent focus:outline-none block w-full py-3 px-4"
                                />
                            </div>
                        </div>
                    )}

                    <div>
                        <label className="block mb-2 text-sm font-medium text-gray-900">
                            {isRegister ? "Email" : "Email or Username"}
                        </label>
                        <div className="relative text-gray-400">
                            <span className="absolute inset-y-0 left-0 flex items-center pl-3">
                                <MailIcon size={20} />
                            </span>
                            <input
                                type="text"
                                name="login_name"
                                value={formData.login_name}
                                onChange={onChange}
                                placeholder={isRegister ? "Email" : "Email or Username"}
                                className="pl-11 bg-gray-50 text-gray-600 border border-gray-300 sm:text-sm rounded-lg focus:ring-1 focus:ring-gray-400 focus:border-transparent focus:outline-none block w-full py-3 px-4"
                            />
                        </div>
                    </div>

                    <div className="pb-2">
                        <label className="block mb-2 text-sm font-medium text-gray-900">Password</label>
                        <div className="relative text-gray-400">
                            <span className="absolute inset-y-0 left-0 flex items-center pl-3">
                                <LockKeyholeIcon size={20} />
                            </span>
                            <input
                                type="password"
                                name="password"
                                value={formData.password}
                                onChange={onChange}
                                placeholder="••••••••••"
                                className="pl-11 bg-gray-50 text-gray-600 border border-gray-300 sm:text-sm rounded-lg focus:ring-1 focus:ring-gray-400 focus:border-transparent focus:outline-none block w-full py-3 px-4"
                                autoComplete="new-password"
                            />
                        </div>
                    </div>

                    {error && (
                        <p className="flex items-center gap-2 text-sm text-red-500">
                            <TriangleAlertIcon size={14} />
                            {error}
                        </p>
                    )}

                    <button
                        onClick={handleSubmit}
                        className="w-full font-medium rounded-lg text-sm px-5 py-2.5 text-center focus:ring-4 focus:outline-none"
                        style={{ background: "#4F46E5", color: "#FFFFFF" }}
                    >
                        {isRegister ? "Register" : "Login"}
                    </button>

                    <div className="text-sm font-light" style={{ color: "#6B7280" }}>
                        {isRegister ? "Already have an account? " : "Don't have an account yet? "}
                        <button
                            className="font-medium hover:underline"
                            style={{ color: "#4F46E5" }}
                            onClick={() => { setIsRegister((prev) => !prev); setError(null); }}
                        >
                            {isRegister ? "Login" : "Sign Up"}
                        </button>
                    </div>
                </div>

                <div className="relative flex py-6 items-center">
                    <div className="grow border-t border-gray-200" />
                    <span className="shrink mx-4 font-medium text-gray-500 text-sm">OR</span>
                    <div className="grow border-t border-gray-200" />
                </div>

                <div className="flex justify-center">
                    <div style={{colorScheme: "light"}}>
                    <GoogleLogin
                        theme="filled_black"
                        onSuccess={async (response) => {
                            const { error } = await client.POST("/auth/google", {
                                body: { credential: response.credential! } as never,
                            });
                            if (error) {
                                setError((error as { detail?: string }).detail ?? "Google login failed");
                                return;
                            }
                            await refreshUser();
                            navigate("/workspaces");
                        }}
                        onError={() => setError("Google login failed")}
                    />
                    </div>
                </div>
            </div>
        </Root>
    );
}
