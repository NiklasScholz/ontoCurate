import { useState, type ChangeEvent } from "react";
import Root from "../components/Root";

export default function LoginPage() {
    const [formData, setFormData] = useState({
        username: "",
        password: "",
    });

    const onChange = (e: ChangeEvent<HTMLInputElement>) => {
        setFormData((prev) => ({
            ...prev,
            [e.target.name]: e.target.value,
        }));
    };

    return (
        <Root>
            <div className="bg-nord6 flex w-120 flex-col gap-2 rounded p-4 shadow-xl">
                <h1 className="mb-4 text-center text-xl">Login</h1>
                <input
                    type="text"
                    placeholder="Username"
                    name="username"
                    value={formData.username}
                    onChange={onChange}
                    className="border-nord4 h-7 rounded border-2 px-2"
                />
                <input
                    type="text"
                    placeholder="Password"
                    name="password"
                    value={formData.password}
                    onChange={onChange}
                    className="border-nord4 h-7 rounded border-2 px-2"
                />
                <div className="flex justify-center">
                    <button
                        className="bg-nord8 h-7 rounded px-2"
                        onClick={() => {}}
                    >
                        Submit
                    </button>
                </div>
            </div>
        </Root>
    );
}
