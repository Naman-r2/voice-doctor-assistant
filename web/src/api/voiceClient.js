import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

// One client for the whole app. It owns the mic, the WebRTC connection and the event stream.
export const client = new PipecatClient({
  transport: new SmallWebRTCTransport({
    iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
  }),
  enableMic: true,
  enableCam: false,
});

export const OFFER_ENDPOINT = "/api/offer";
