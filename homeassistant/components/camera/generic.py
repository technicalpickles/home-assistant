"""
Support for IP Cameras.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/camera.generic/
"""
import logging

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
import voluptuous as vol

from homeassistant.const import CONF_NAME, CONF_USERNAME, CONF_PASSWORD
from homeassistant.exceptions import TemplateError
from homeassistant.components.camera import PLATFORM_SCHEMA, Camera
from homeassistant.helpers import config_validation as cv, template


_LOGGER = logging.getLogger(__name__)

CONF_AUTHENTICATION = 'authentication'
CONF_STILL_IMAGE_URL = 'still_image_url'
CONF_LIMIT_REFETCH_TO_URL_CHANGE = 'limit_refetch_to_url_change'
DEFAULT_NAME = 'Generic Camera'
BASIC_AUTHENTICATION = 'basic'
DIGEST_AUTHENTICATION = 'digest'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    # pylint: disable=no-value-for-parameter
    vol.Required(CONF_STILL_IMAGE_URL): vol.Any(vol.Url(), cv.template),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_USERNAME): cv.string,
    vol.Optional(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_AUTHENTICATION, default='BASIC_AUTHENTICATION'):
    vol.In([BASIC_AUTHENTICATION, DIGEST_AUTHENTICATION]),
    vol.Optional(CONF_LIMIT_REFETCH_TO_URL_CHANGE, default=False): cv.boolean,
})


# pylint: disable=unused-argument
def setup_platform(hass, config, add_devices_callback, discovery_info=None):
    """Setup a generic IP Camera."""
    add_devices_callback([GenericCamera(config)])


# pylint: disable=too-many-instance-attributes
class GenericCamera(Camera):
    """A generic implementation of an IP camera."""

    def __init__(self, device_info):
        """Initialize a generic camera."""
        super().__init__()
        self._name = device_info.get(CONF_NAME)
        self._authentication = device_info.get(CONF_AUTHENTICATION)
        self._username = device_info.get(CONF_USERNAME)
        self._password = device_info.get(CONF_PASSWORD)
        self._still_image_url = device_info[CONF_STILL_IMAGE_URL]
        self._limit_refetch = device_info[CONF_LIMIT_REFETCH_TO_URL_CHANGE]
        self._last_url = None
        self._last_image = None

    def camera_image(self):
        """Return a still image response from the camera."""
        try:
            url = template.render(self.hass, self._still_image_url)
        except TemplateError as err:
            _LOGGER.error('Error parsing template %s: %s',
                          self._still_image_url, err)
            return self._last_image

        if url == self._last_url and self._limit_refetch:
            return self._last_image

        if self._username and self._password:
            if self._authentication == DIGEST_AUTHENTICATION:
                auth = HTTPDigestAuth(self._username, self._password)
            else:
                auth = HTTPBasicAuth(self._username, self._password)
            try:
                response = requests.get(url, auth=auth, timeout=10)
            except requests.exceptions.RequestException as error:
                _LOGGER.error('Error getting camera image: %s', error)
                return None
        else:
            try:
                response = requests.get(url, timeout=10)
            except requests.exceptions.RequestException as error:
                _LOGGER.error('Error getting camera image: %s', error)
                return None

        self._last_url = url
        self._last_image = response.content
        return self._last_image

    @property
    def name(self):
        """Return the name of this device."""
        return self._name
