# Voice: Wyoming satellite → Assist pipeline → GoodVibes agent

The GoodVibes conversation entity is a normal Home Assistant conversation agent,
so it can serve as the brain of an [Assist pipeline](https://www.home-assistant.io/voice_control/)
driven by a [Wyoming](https://www.home-assistant.io/integrations/wyoming/) voice
satellite. Speech-to-text, text-to-speech, and wake-word detection are provided
by Home Assistant and Wyoming; GoodVibes handles the conversation turn.

## The path a spoken request takes

1. A Wyoming satellite (an ESP32 "Voice PE" puck, a Raspberry Pi running the
   satellite software, or any Wyoming device) captures audio after its wake word
   and streams it to Home Assistant.
2. The Assist **pipeline** you assign to that satellite runs speech-to-text,
   then hands the transcribed text to the pipeline's **conversation agent**.
3. When that agent is the **GoodVibes** conversation entity, the turn streams to
   the GoodVibes daemon (see [Conversation agent](conversation.md)); the spoken
   reply is streamed back and the pipeline runs text-to-speech to the satellite.

## Setup

1. **Add the Wyoming satellite.** Follow the
   [Wyoming integration docs](https://www.home-assistant.io/integrations/wyoming/).
   The satellite appears as an `assist_satellite` device.
2. **Create an Assist pipeline.** In *Settings → Voice assistants → Add
   assistant*, choose your speech-to-text and text-to-speech engines.
3. **Select GoodVibes as the conversation agent.** In that pipeline's
   *Conversation agent* dropdown, pick the **GoodVibes** entity
   (`conversation.goodvibes`). It is listed automatically once the integration is
   set up — the conversation entity registers itself as a selectable agent and
   advertises support for every language (`*`) and for controlling Home
   Assistant.
4. **Assign the pipeline to the satellite.** On the satellite device, set its
   pipeline to the one you just created.

That is the whole integration-side requirement: no extra flag has to be toggled
for GoodVibes to be a valid pipeline agent. The turn a satellite produces carries
its `device_id` and `satellite_id`; the GoodVibes entity forwards both (and the
device's area, when known) to the daemon as turn context, so the daemon knows
which room the request came from.

## What GoodVibes does, and what it deliberately leaves to Home Assistant / Wyoming

GoodVibes owns the **conversation turn**: it takes the transcribed text, streams
it to the daemon, and returns the spoken answer. It does **not** re-implement the
parts of the voice stack that Home Assistant and Wyoming already own:

- **Wake-word detection** runs on the Wyoming satellite / openWakeWord, not here.
- **Speech-to-text and text-to-speech** are pipeline stages you choose in Home
  Assistant; GoodVibes never touches audio.
- **Full-duplex / continuous "talk mode"** (barge-in, continued conversation,
  timers, announcements) is Assist-satellite and pipeline behavior. GoodVibes
  returns one answer per turn and lets the pipeline drive the exchange, rather
  than duplicating that machinery.

If you need those capabilities, configure them on the Wyoming device and the
Assist pipeline — they compose with GoodVibes as the agent, and reimplementing
them inside this integration would only fight the platform.
