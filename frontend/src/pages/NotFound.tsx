import { useNavigate } from "react-router-dom";
import Root from "../components/Root";

export default function NotFound() {
    const navigate = useNavigate();

    return (
        <Root>
            <h1 className="text-nord6 text-4xl font-bold">404: Not found</h1>
            <button onClick={() => navigate("/")}>Back to login</button>
        </Root>
    );
}
