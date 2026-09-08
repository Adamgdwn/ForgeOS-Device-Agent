#!/bin/sh
# Program the Samsung codec directly through Linux ALSA.
set -eu
root=/os/root
printf 'ctl.forge { type hw card 0 }\n' > /run/forge-alsa.conf
export ALSA_CONFIG_PATH=/run/forge-alsa.conf
mixer() {
  "$root/usr/lib/ld-linux-armhf.so.3" --library-path "$root/usr/lib/arm-linux-gnueabihf" \
    "$root/usr/bin/amixer" -D forge cset "name=$1" "$2" >/dev/null
}
mixer 'AudioMixer Mixer En' On
mixer 'AudioMixer SRC1 En' Off
mixer 'AudioMixer SRC2 En' Off
mixer 'AudioMixer SRC3 En' Off
mixer 'AudioMixer CH1 Mixer En' On
mixer 'AudioMixer CH2 Mixer En' Off
mixer 'AudioMixer CH3 Mixer En' Off
mixer 'AudioMixer CH4 Mixer En' Off
mixer 'AudioMixer CH1 DOUT Select' AIF4IN
mixer 'MonoMix Mode' Disable
mixer 'Chargepump Mode' CLASS-G-A
mixer 'DNC Max Gain' 24
mixer 'HP HP On' 0
mixer 'EP EP On' 0
mixer 'SPK SPK On' 1
mixer 'AudioMixer MIX1_LVL' 0
mixer 'DAC Gain' 114
mixer 'Speaker Volume' 3
echo 'Linux speaker route configured'
