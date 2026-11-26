import { createRoot } from "react-dom/client";
import { PipecatClientAudio, PipecatClientProvider } from "@pipecat-ai/client-react";
import { client } from "./api/voiceClient.js";
import App from "./App.jsx";
import "./styles/index.css";

createRoot(document.getElementById("root")).render(
  <PipecatClientProvider client={client}>
    <App />
    {/* Plays the agent's voice. */}
    <PipecatClientAudio />
  </PipecatClientProvider>,
);
