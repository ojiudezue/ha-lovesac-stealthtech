# Lovesac StealthTech for Home Assistant

A local Home Assistant integration for the [Lovesac StealthTech Sound + Charge](https://www.lovesac.com/learn-about-sactionals-stealthtech-sound-charge) system, the Harman Kardon audio package built into Sactionals. It talks to the hub directly over Bluetooth Low Energy. No cloud, no account, no Lovesac app required once set up.

## What you get

- Media player: power, volume, mute, input selection (HDMI ARC, Bluetooth, AUX, Optical), sound modes (Movies, Music, TV, News), and play, pause and skip when the source is Bluetooth
- A standalone input dropdown and a current input sensor, so switching inputs from a dashboard takes one tap
- Equalizer controls: bass, treble, center volume, rear volume, balance
- Quiet Couch Mode switch. This is Lovesac's night listening feature: it turns down the speakers and subwoofer embedded in the seats and limits peaks, while the center channel keeps carrying the audio. [Lovesac's description](https://www.lovesac.com/stealthtech-app)
- Subwoofer connection sensor
- Diagnostics: firmware versions (MCU, DSP, EQ), audio capability, connection health, last contact, and raw layout, covering and arm type values
- A sync button that refreshes state from the hub on demand

## StealthTech Audio capability

The hub is HDMI ARC only and decodes Dolby Digital 5.1, with Pro Logic II upmixing. There is no Atmos and no DTS support in the hardware as shipped, per the [libstealthtech hardware teardown](https://github.com/jackspirou/libstealthtech). The integration surfaces this as a diagnostic sensor so the answer lives on the device page instead of in a forum thread.

## Requirements

- Home Assistant with the Bluetooth integration
- A Bluetooth adapter in range of the hub, or an [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html) (ESP32, firmware 2022.9.3 or newer for active connections)
- Note: Shelly Bluetooth proxies will not work for control. They relay advertisements only and cannot open connections, per the [Home Assistant Bluetooth documentation](https://www.home-assistant.io/integrations/bluetooth/). A Shelly near the couch lets Home Assistant discover the hub but never control it.

## Install

Via [HACS](https://hacs.xyz): add this repository as a custom repository (category: Integration), install, restart Home Assistant. The hub should appear as a discovered device if it is advertising; otherwise add the integration manually and enter its Bluetooth address.

Manual: copy `custom_components/lovesac_stealthtech` into your `config/custom_components` directory and restart.

## The one thing to know before getting started 

The hub accepts a single Bluetooth control connection. The Lovesac app and this integration cannot both hold it at once. The integration connects briefly on a schedule and for commands, then disconnects, so the app still works between polls. If controls stop responding, the app on someone's phone is almost always the reason, and the connection health sensor will say so.

A related detail that works in your favor: Bluetooth audio streaming to the hub is a separate link from the control connection. You can stream music from a phone while Home Assistant keeps control.

Writes are ignored by the hub while it is powered off, except power on itself. Equalizer changes made while the system is off will not stick.

## Help build the enum table

Three diagnostic sensors report raw configuration bytes from the hub: Layout (raw), Couch Cover (raw) and Couch Arm Type (raw). The firmware names layouts like Straight, L-shape, U-shape and Pit, but nobody has published which number means which. If you own the system, you can help fill in the table: [open an issue](https://github.com/ojiudezue/ha-lovesac-stealthtech/issues) with the raw values these sensors show and what the Lovesac app says your layout, arm style and fabric are. Once a value is confirmed, the sensor starts showing the name instead of the number, and the raw byte stays visible as a `raw_value` attribute.

## Credits

- [homebridge-lovesac-stealthtech](https://github.com/ohmantics/homebridge-lovesac-stealthtech) by Alex Rosenberg, the first working implementation of this protocol and the reference for command framing
- [libstealthtech](https://github.com/jackspirou/libstealthtech) by Jack Spirou, whose protocol mapping, firmware analysis and hardware teardown documentation made a clean room Python implementation possible

Both are MIT licensed, as is this project. See LICENSE.

This project is not affiliated with, endorsed by, or supported by Lovesac or Harman Kardon. StealthTech and Sactionals are trademarks of The Lovesac Company. Use at your own risk.
