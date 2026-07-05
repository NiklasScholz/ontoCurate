import { ArrowLeftIcon, ArrowRightIcon, XIcon } from "lucide-react";
import Panel from "../components/Panel.tsx";

export default function CurationDetail({
    onClose,
    onPrevious,
    onNext,
}: {
    onClose: () => void;
    onPrevious: () => void;
    onNext: () => void;
}) {
    return (
        <Panel className="flex flex-col gap-2">
            <div className="flex justify-end">
                <button onClick={() => onPrevious()}>
                    <ArrowLeftIcon />
                </button>
                <button onClick={() => onClose()}>
                    <XIcon />
                </button>
                <button onClick={() => onNext()}>
                    <ArrowRightIcon />
                </button>
            </div>
        </Panel>
    );
}
