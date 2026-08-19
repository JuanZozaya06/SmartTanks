from src.device_claim import create_factory_credentials, verify_setup_pin


def test_provisioned_credentials_are_unique_and_verifiable() -> None:
    first = create_factory_credentials("smarttank-84f703123456")
    second = create_factory_credentials("smarttank-84f703654321")

    assert first.device_id != second.device_id
    assert first.device_secret != second.device_secret
    assert len(first.setup_pin) == 8
    assert verify_setup_pin(first.setup_pin, first.setup_pin_salt, first.setup_pin_hash)
    assert not verify_setup_pin("00000000", first.setup_pin_salt, first.setup_pin_hash)
