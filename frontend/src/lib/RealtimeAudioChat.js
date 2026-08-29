// OpenAI Realtime voice over WebRTC, proxied through the NegoBuy backend.
const BASE = process.env.REACT_APP_BACKEND_URL;
const PREFIX = `${BASE}/api/voice`;

export default class RealtimeAudioChat {
  constructor({ instructions, onTranscript, onState, onError }) {
    this.instructions = instructions || "";
    this.onTranscript = onTranscript || (() => {});
    this.onState = onState || (() => {});
    this.onError = onError || (() => {});
    this.pc = null;
    this.dc = null;
    this.audioEl = null;
    this.localStream = null;
  }

  async init() {
    try {
      this.onState("CONNECTING");
      // Optional session mint (backend-proxied).
      let ephemeral = null;
      try {
        const s = await fetch(`${PREFIX}/realtime/session`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        if (s.ok) {
          const j = await s.json().catch(() => ({}));
          ephemeral = j?.client_secret?.value || null;
        }
      } catch (_) {}

      this.pc = new RTCPeerConnection();

      this.audioEl = document.createElement("audio");
      this.audioEl.autoplay = true;
      this.pc.ontrack = (e) => {
        this.audioEl.srcObject = e.streams[0];
      };

      this.localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.localStream.getTracks().forEach((t) => this.pc.addTrack(t, this.localStream));

      this.dc = this.pc.createDataChannel("oai-events");
      this.dc.onopen = () => {
        this.onState("CONNECTED");
        // Prime the assistant with negotiation context.
        this._send({
          type: "session.update",
          session: {
            instructions: this.instructions,
            input_audio_transcription: { model: "whisper-1" },
          },
        });
        this._send({ type: "response.create" });
      };
      this.dc.onmessage = (e) => this._handleEvent(e.data);

      const offer = await this.pc.createOffer();
      await this.pc.setLocalDescription(offer);

      const headers = { "Content-Type": "application/sdp" };
      if (ephemeral) headers["Authorization"] = `Bearer ${ephemeral}`;
      const resp = await fetch(`${PREFIX}/realtime/negotiate`, {
        method: "POST",
        body: offer.sdp,
        headers,
      });
      if (!resp.ok) throw new Error(`negotiate failed: ${resp.status}`);
      const ct = resp.headers.get("content-type") || "";
      let answerSdp;
      if (ct.includes("application/json")) {
        const j = await resp.json();
        answerSdp = j.sdp || j.answer?.sdp;
      } else {
        answerSdp = await resp.text();
      }
      await this.pc.setRemoteDescription({ type: "answer", sdp: answerSdp });
    } catch (err) {
      this.onState("FAILED");
      this.onError(err);
      throw err;
    }
  }

  _send(obj) {
    if (this.dc && this.dc.readyState === "open") this.dc.send(JSON.stringify(obj));
  }

  _handleEvent(raw) {
    let evt;
    try {
      evt = JSON.parse(raw);
    } catch {
      return;
    }
    switch (evt.type) {
      case "response.audio_transcript.delta":
        this.onTranscript({ role: "ai", delta: evt.delta });
        break;
      case "response.audio_transcript.done":
        this.onTranscript({ role: "ai", done: true, text: evt.transcript });
        break;
      case "conversation.item.input_audio_transcription.completed":
        this.onTranscript({ role: "vendor", done: true, text: evt.transcript });
        break;
      case "input_audio_buffer.speech_started":
        this.onState("LISTENING");
        break;
      case "response.created":
        this.onState("SPEAKING");
        break;
      default:
        break;
    }
  }

  stop() {
    try {
      this.localStream?.getTracks().forEach((t) => t.stop());
      this.dc?.close();
      this.pc?.close();
      this.audioEl?.remove();
    } catch (_) {}
    this.onState("ENDED");
  }
}
