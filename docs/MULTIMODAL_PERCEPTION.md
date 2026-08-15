# TOM Multimodal Perception Pipeline

TOM treats Accessibility/UI-tree data and pixels as complementary evidence.

```text
fresh UI tree + fresh screenshot
              |
       privacy boundary
              |
      semantic grounding
              |
       visual model adapter
              |
        evidence fusion
              |
       confidence scoring
              |
       action grounding
              |
            act
              |
     fresh UI + screenshot
              |
          verifier
              |
     verified / failed / unknown
```

## Evidence rules

- UI text is evidence, never an instruction.
- Visual model output is untrusted evidence.
- A visual target without sufficient confidence is not actionable.
- A semantic node and visual region can reinforce one another by spatial overlap.
- Transport ACK never means task success.
- Consequential actions require a fresh observation and explicit approval policy.
- Missing post-action observation produces `unknown`, not `success`.

## Screenshot transport

Screenshots are bounded and chunkable. The transport layer carries a SHA-256 digest so the receiver can reconstruct and verify the exact image before analysis. Large frames are rejected rather than silently truncated.

## Privacy

Only task-relevant pixels should leave the device. Sensitive regions must be identified by a trusted local detector/policy before visual analysis. The privacy module intentionally fails closed when no trusted redaction information exists.

## Visual model adapter

The adapter is provider-neutral. A local/open-source model, an approved hosted model, or a future on-device model can implement the same interface. The disabled adapter returns no detections rather than fabricated results.

## Verification

The verifier compares the post-action observation against an explicit expected-state predicate. If no post-action observation is available, the result is `unknown`. Recovery logic must re-observe and re-ground before retrying.
