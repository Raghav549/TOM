# Dream TOM Roadmap

This is the implementation contract for taking TOM from a strong runtime foundation to a production personal agent.

## Done / present in main

- Provider-neutral agent runtime and structured planning.
- Tool permissions and approval gates.
- Durable memory interfaces.
- Android bridge, accessibility actions, screenshots and event stream.
- Post-action verification and live replanning hooks.
- Multimodal perception contracts.
- Full-duplex Android voice transport with local fallback.
- Streaming ASR/VAD/turn-detection/TTS adapters.
- Lightweight live frontend for task events.

## Next implementation gates

1. **Runtime hardening**
   - deterministic configuration validation
   - structured startup diagnostics
   - health/readiness separation
   - graceful shutdown and resource lifecycle
   - typed error taxonomy

2. **Real provider layer**
   - OpenAI-compatible LLM configuration
   - vision configuration
   - streaming ASR configuration
   - streaming TTS configuration
   - explicit model capability reporting
   - no fake fallback when a provider is missing

3. **Browser automation**
   - Playwright adapter
   - browser session lifecycle
   - screenshot/UI grounding
   - action verification
   - safe navigation and download policy
   - approval for external side effects

4. **Android production bridge**
   - authenticated device enrollment
   - reconnect/backoff
   - idempotent action IDs
   - action timeout/cancellation
   - foreground/background lifecycle handling
   - capability negotiation

5. **Public integrations**
   - email
   - calendar
   - messaging
   - storage/files
   - search
   - maps/location
   - payments only behind explicit approval and provider-specific adapters

6. **Voice**
   - real streaming ASR model deployment
   - real neural VAD deployment
   - Smart Turn model deployment
   - real streaming TTS deployment
   - interruption cancellation
   - multilingual/Hinglish evaluation

7. **Memory and personalization**
   - durable episodic memory
   - semantic retrieval
   - explicit user-controlled retention/deletion
   - task history and summaries

8. **Security**
   - device authentication
   - secret management
   - scoped credentials
   - audit log
   - rate limiting
   - origin/CORS policy
   - encrypted transport

9. **Observability and reliability**
   - structured logs
   - metrics
   - traces/correlation IDs
   - task replay/debugging
   - retry policies
   - circuit breakers

10. **Production validation**
    - unit/integration tests
    - Android end-to-end tests
    - browser end-to-end tests
    - voice latency/quality tests
    - failure-injection tests
    - deployment smoke tests

## Definition of done

TOM is considered production-ready only when configured capabilities are real and exercised end-to-end. If a model, provider, credential, device adapter, or external integration is not configured, TOM must report it as unavailable rather than pretending it works.
