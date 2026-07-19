import { useState } from "react";
import { HelpCircleIcon } from "lucide-react";
import HelpDialog from "./HelpDialog";
import Popup from "./Popup";

export default function HelpButton() {
    const [show, setShow] = useState(false);

    return (
        <>
            <button
                onClick={() => setShow(true)}
                className="text-nord6 opacity-80 hover:opacity-100"
                aria-label="Help"
            >
                <HelpCircleIcon size={20} />
            </button>
            <Popup show={show}>
                <HelpDialog onClose={() => setShow(false)} />
            </Popup>
        </>
    );
}
