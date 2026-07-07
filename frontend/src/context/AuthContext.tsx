import { useEffect, useState, type ReactNode } from "react";
import { client } from "../client";
import { AuthContext, type User } from "./useAuth";

export function AuthProvider({ children }: { children: ReactNode }) {
    const [currentUser, setCurrentUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);

    const refreshUser = async () => {
        const { data } = await client.GET("/auth/me");
        setCurrentUser((data as User) ?? null);
    };

    useEffect(() => {
        let cancelled = false;
        client.GET("/auth/me").then(({ data }) => {
            if (!cancelled) {
                setCurrentUser((data as User) ?? null);
                setLoading(false);
            }
        });
        return () => { cancelled = true; };
    }, []);

    const logout = async () => {
        await client.POST("/auth/logout");
        setCurrentUser(null);
    };

    const deleteAccount = async () => {
        await client.DELETE("/auth/me");
        setCurrentUser(null);
    };

    return (
        <AuthContext.Provider value={{ currentUser, loading, logout, deleteAccount, refreshUser }}>
            {children}
        </AuthContext.Provider>
    );
}
