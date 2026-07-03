from swagger import swagger_config
from version import get_version


def test_swagger_uses_version_file_and_real_auth_scheme():
    assert swagger_config["info"]["version"] == get_version()
    assert swagger_config["security"] == [{"ApiKeyAuth": []}]
