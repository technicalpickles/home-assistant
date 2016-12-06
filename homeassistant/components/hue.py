"""
Support for Hue, lights, groups, and scenes.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/hue/
"""
import json
import logging
import os
import socket
from datetime import timedelta

import voluptuous as vol

from homeassistant.config import load_yaml_config_file
from homeassistant.const import (CONF_FILENAME, CONF_HOST)
from homeassistant.loader import get_component
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = ['phue==0.9']

# Track previously setup bridges
_CONFIGURED_BRIDGES = {}
# Map ip to request id for configuring
_CONFIGURING = {}
_LOGGER = logging.getLogger(__name__)

DEFAULT_ALLOW_UNREACHABLE = False
DOMAIN = "hue"
SERVICE_HUE_SCENE = "activate_scene"

MIN_TIME_BETWEEN_SCANS = timedelta(seconds=10)
MIN_TIME_BETWEEN_FORCED_SCANS = timedelta(milliseconds=100)

PHUE_CONFIG_FILE = 'phue.conf'

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_FILENAME): cv.string,
    })
})

ATTR_GROUP_NAME = "group_name"
ATTR_SCENE_NAME = "scene_name"
SCENE_SCHEMA = vol.Schema({
    vol.Required(ATTR_GROUP_NAME): cv.string,
    vol.Required(ATTR_SCENE_NAME): cv.string,
})


def _find_host_from_config(hass, filename=PHUE_CONFIG_FILE):
    """Attempt to detect host based on existing configuration."""
    path = hass.config.path(filename)

    if not os.path.isfile(path):
        return None

    try:
        with open(path) as inp:
            return next(json.loads(''.join(inp)).keys().__iter__())
    except (ValueError, AttributeError, StopIteration):
        # ValueError if can't parse as JSON
        # AttributeError if JSON value is not a dict
        # StopIteration if no keys
        return None


def setup(hass, config):
    """Setup the Hue ecosystem."""
    # Default needed in case of discovery
    filename = config.get(CONF_FILENAME, PHUE_CONFIG_FILE)

    conf = config[DOMAIN]

    host = conf.get(CONF_HOST, None)

    if host is None:
        host = _find_host_from_config(hass, filename)

    if host is None:
        _LOGGER.error('No host found in configuration')
        return False

    # Only act if we are not already configuring this host
    if host in _CONFIGURING or \
            socket.gethostbyname(host) in _CONFIGURED_BRIDGES:
        return

    setup_bridge(host, hass, filename)


def setup_bridge(host, hass, filename):
    """Setup a phue bridge based on host parameter."""
    import phue

    try:
        bridge = phue.Bridge(
            host,
            config_file_path=hass.config.path(filename))
    except ConnectionRefusedError:  # Wrong host was given
        _LOGGER.error("Error connecting to the Hue bridge at %s", host)

        return

    except phue.PhueRegistrationException:
        _LOGGER.warning("Connected to Hue at %s but not registered.", host)

        request_configuration(host, hass, filename)

        return

    # If we came here and configuring this host, mark as done
    if host in _CONFIGURING:
        request_id = _CONFIGURING.pop(host)

        configurator = get_component('configurator')

        configurator.request_done(request_id)

    _CONFIGURED_BRIDGES[socket.gethostbyname(host)] = True

    # create a service for calling run_scene directly on the bridge,
    # used to simplify automation rules.
    def hue_activate_scene(call):
        """Service to call directly directly into bridge to set scenes."""
        group_name = call.data[ATTR_GROUP_NAME]
        scene_name = call.data[ATTR_SCENE_NAME]
        bridge.run_scene(group_name, scene_name)

    descriptions = load_yaml_config_file(
        os.path.join(os.path.dirname(__file__), 'services.yaml'))
    hass.services.register(DOMAIN, SERVICE_HUE_SCENE, hue_activate_scene,
                           descriptions.get(SERVICE_HUE_SCENE),
                           schema=SCENE_SCHEMA)


def request_configuration(host, hass, filename):
    """Request configuration steps from the user."""
    configurator = get_component('configurator')

    # We got an error if this method is called while we are configuring
    if host in _CONFIGURING:
        configurator.notify_errors(
            _CONFIGURING[host], "Failed to register, please try again.")

        return

    # pylint: disable=unused-argument
    def hue_configuration_callback(data):
        """The actions to do when our configuration callback is called."""
        setup_bridge(host, hass, filename)

    _CONFIGURING[host] = configurator.request_config(
        hass, "Philips Hue", hue_configuration_callback,
        description=("Press the button on the bridge to register Philips Hue "
                     "with Home Assistant."),
        entity_picture="/static/images/logo_philips_hue.png",
        description_image="/static/images/config_philips_hue.jpg",
        submit_caption="I have pressed the button"
    )
