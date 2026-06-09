import { useParams } from "react-router-dom";
import Root from "../components/Root";

export default function WorkspacePage() {
    const { id } = useParams();

    return (
        <Root>
            <div>TODO {id}</div>
        </Root>
    );
}
