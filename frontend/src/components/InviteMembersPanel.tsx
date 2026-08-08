import { useState } from "react";
import { PlusIcon, XIcon } from "lucide-react";
import Spinner from "./Spinner";
import { client, getErrorMessage } from "../client";

export type PendingInvite = { user_info: string; role: "owner" | "editor" };
export type ExistingMember = { id: string; email: string; name: string | null; role: string };

type Props = {
    invites: PendingInvite[];
    onChange: (invites: PendingInvite[]) => void;
    currentUserEmail?: string;
    existingMembers?: ExistingMember[];
    onRemoveMember?: (member: ExistingMember) => void;
};

export default function InviteMembersSection({ invites, onChange, currentUserEmail, existingMembers, onRemoveMember }: Props) {
    const [userinfo, setUserinfo] = useState("");
    const [role, setRole] = useState<"owner" | "editor">("editor");
    const [lookupError, setLookupError] = useState<string | null>(null);
    const [checking, setChecking] = useState(false);

    const add = async () => {
        const trimmed = userinfo.trim();
        if (!trimmed || invites.some((i) => i.user_info === trimmed)) return;

        setChecking(true);
        setLookupError(null);

        const { error } = await client.GET("/users/lookup", {
            params: { query: { user_info: trimmed } },
        });

        setChecking(false);

        if (error) {
            setLookupError(getErrorMessage(error, "User not found"));
            return;
        }

        onChange([...invites, { user_info: trimmed, role }]);
        setUserinfo("");
        setRole("editor");
    };

    const remove = (target: string) =>
        onChange(invites.filter((i) => i.user_info !== target));

    const hasRows = currentUserEmail || (existingMembers && existingMembers.length > 0) || invites.length > 0;

    return (
        <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
                <div className="flex gap-2">
                    <input
                        type="text"
                        placeholder="User info"
                        value={userinfo}
                        onChange={(e) => setUserinfo(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && add()}
                        className="border-nord4 h-8 flex-1 rounded border-2 px-2 text-sm"
                    />
                    <select
                        value={role}
                        onChange={(e) => setRole(e.target.value as "owner" | "editor")}
                        className="border-nord4 h-8 rounded border-2 px-2 text-sm"
                    >
                        <option value="editor">Editor</option>
                        <option value="owner">Owner</option>
                    </select>
                    <button
                        onClick={add}
                        disabled={!userinfo.trim() || checking}
                        className="bg-nord8 flex h-8 items-center gap-1 rounded px-3 text-sm text-white disabled:opacity-40"
                    >
                        {checking ? <Spinner /> : <><PlusIcon size={14} />Add</>}
                    </button>
                </div>
                {lookupError && <p className="text-nord11 text-sm">{lookupError}</p>}
            </div>

            {hasRows && (
                <div className="flex flex-col gap-1">
                    {currentUserEmail && (
                        <div className="bg-nord4 flex items-center justify-between rounded px-3 py-1.5 text-sm opacity-60">
                            <span>{currentUserEmail}</span>
                            <div className="flex items-center gap-2">
                                <span className="bg-nord8 rounded px-2 py-0.5 text-xs text-white">
                                    owner
                                </span>
                                <span className="w-[14px]" />
                            </div>
                        </div>
                    )}
                    {existingMembers?.map((member) => (
                        <div
                            key={member.id}
                            className="bg-nord4 flex items-center justify-between rounded px-3 py-1.5 text-sm opacity-60"
                        >
                            <span>{member.email}{member.name && ` (${member.name})`}</span>
                            <div className="flex items-center gap-2">
                                <span className="bg-nord8 rounded px-2 py-0.5 text-xs text-white">
                                    {member.role}
                                </span>
                                {onRemoveMember ? (
                                    <button
                                        onClick={() => onRemoveMember(member)}
                                        className="hover:text-nord11"
                                    >
                                        <XIcon size={14} />
                                    </button>
                                ) : (
                                    <span className="w-[14px]" />
                                )}
                            </div>
                        </div>
                    ))}
                    {invites.map((invite) => (
                        <div
                            key={invite.user_info}
                            className="bg-nord4 flex items-center justify-between rounded px-3 py-1.5 text-sm"
                        >
                            <span>{invite.user_info}</span>
                            <div className="flex items-center gap-2">
                                <span className="bg-nord8 rounded px-2 py-0.5 text-xs text-white">
                                    {invite.role}
                                </span>
                                <button
                                    onClick={() => remove(invite.user_info)}
                                    className="hover:text-nord11"
                                >
                                    <XIcon size={14} />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
