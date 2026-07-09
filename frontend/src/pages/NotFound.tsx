import { Link } from "react-router-dom";
import Root from "../components/Root";

export default function NotFound() {
    return (
        <Root>
            <div>
                <h1 className="text-nord6 text-4xl font-bold">
                    404: Not found
                </h1>
                <Link to="/" className="text-nord6 underline">
                    Back to login
                </Link>
            </div>
        </Root>
    );
}
