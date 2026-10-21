# Reference set

Material gathered on 2 to 3 Oct 2026 to ground the herb twin. Read the file that matches
the work in hand. Each file marks what was verified and what was not.

| File | Use it when |
|---|---|
| `../data-catalogue.md` | choosing a dataset, benchmark or API; checking a licence |
| `../literature.md` | citing prior work; looking up a threshold from a controlled experiment |
| `herb-care-packs.md` | writing a species pack; deciding what is normal for a plant in this season |
| `seasonal-norms.md` | saying whether a plant's look is normal for this UK month; what changes next; which signs are a real problem |
| `differential-diagnosis.md` | writing the observe or recommend prompt; deciding when to ask the user |
| `pests-and-diseases.md` | handling a pest or disease call; finding reference photos |
| `trait-databases.md` | building the species-facts table from data |
| `herb-growth-facts.md` | setting growth, light or drought-sensitivity parameters |
| `container-physics.md` | parameterising the water bucket for a pot or trough |
| `risk-models.md` | adding a fungal, heat, bolting, pest or frost rule; assigning an evidence tier |
| `light-microclimate-and-open-texts.md` | converting radiation to light, shading, patio temperature bias, feeding, embeddable texts |
| `world-models.md` | planning the learning-track experiment |
| `evaluation-methods.md` | designing the rubric, the rating protocol or the report |
| `users-and-risk-communication.md` | designing the risk strip and recommendation card; quoting impact figures |
| `indoor-mode.md` | designing for plants kept indoors; estimating light from a phone photo; deciding what to ask the user |
| `sponsor-tooling.md` | using Token Factory, Nemotron, NeMo, Tavily or LangSmith features |
| `data-profile.md` | checking what is actually downloaded, its counts and labels, and where the catalogue was wrong |
| `community-and-open-media.md` | pulling real user questions and preference pairs (Stack Exchange), time-lapse video, public-domain herb books, dated UK photos |
| `model-speed-and-cost.md` | choosing where a model run goes (local, Token Factory, subscription CLI): measured time and cost per call |
| `chat-on-nano.md`, `chat-on-lightning.md` | choosing the follow-up chat's model: the what-if and hard-case checks, Nano 3 against Super and Lightning 3.5, and Lightning's tool-call quirks |
| `nemotron-super-vl-probe.md` | Nemotron 3.5 Super VL (Token Factory per token) against GLM-5.3-Flash on the photo step: species, decline, speed, cost; reasoning must be off |
| `nvidia-models.md` | which NVIDIA model does which job and why (Super advises, Nano chats); Nemotron 3 Nano, Super and Ultra on the same advice questions; Ultra as a judge and the held-out rule; headline steadiness; the NVIDIA vision models tried for the photo step |
| `fine-tune-nano-probe.md` | tuning a small model on the advice task; running a GPU job on Nebius (B300 spot, SSH payloads, vLLM serving); what a LoRA-tuned Nemotron 3 Nano 4B scored against Super |
| `magpie-tts-probe.md` | speaking advice with NVIDIA's open Magpie TTS: word error rate by voice (Parakeet round trip), why text normalisation matters, Nebius GPU job setup snags and spot price, comparison with ElevenLabs |
| `soil-area-and-what-to-grow.md` | working out soil type from a photo, location and one question; free location lookups (soil maps, frost dates, pests, flood); what to grow now and which data can back it; licences of the soil and crop sets; the vision model scored on public soil photos, the 155-crop UK sowing calendar, Met Office 1 km frost and sun normals, garden orientation and sun hours from photos |

Evidence tiers used across the set are defined in `risk-models.md`: A peer-reviewed for
this species or pathogen, B borrowed from a related crop, C extension or RHS guidance,
D heuristic.
