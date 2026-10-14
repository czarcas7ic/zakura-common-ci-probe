//! Types and functions for interacting with legacy zcashd key material.

use alloc::string::{String, ToString};
use bip0039::{English, Mnemonic};
use regex::Regex;
use secrecy::{ExposeSecret, SecretVec};
use zcash_protocol::consensus::NetworkConstants;
use zip32::{AccountId, ChildIndex};

// Derives a mnemonic phrase, using the pre-BIP-39 seed as entropy.
//
// zcashd produced a mnemonic from the pre-BIP-39 seed by incrementing the first byte of the
// pre-BIP-39 seed until we found a value that was usable as valid entropy for seed phrase
// generation.
pub fn derive_mnemonic(legacy_seed: &SecretVec<u8>) -> Option<Mnemonic> {
    if legacy_seed.expose_secret().len() != 32 {
        return None;
    }

    let mut offset = 0u8;
    loop {
        let mut entropy = legacy_seed.expose_secret().clone();
        entropy[0] += offset;
        match Mnemonic::<English>::from_entropy(entropy) {
            Ok(m) => {
                return Some(m);
            }
            Err(_) => {
                if offset == 0xFF {
                    return None;
                } else {
                    offset += 1;
                }
            }
        }
    }
}

/// A type-safe wrapper for account identifiers.
///
/// Accounts are 31-bit unsigned integers, and are always treated as hardened in
/// derivation paths.
#[derive(Debug, Default, Copy, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct LegacyAddressIndex(u32);

impl TryFrom<u32> for LegacyAddressIndex {
    type Error = ();

    fn try_from(id: u32) -> Result<Self, Self::Error> {
        // Account IDs are always hardened in derivation paths, so they are effectively at
        // most 31 bits.
        if id < (1 << 31) {
            Ok(Self(id))
        } else {
            Err(())
        }
    }
}

impl From<LegacyAddressIndex> for u32 {
    fn from(id: LegacyAddressIndex) -> Self {
        id.0
    }
}

impl From<LegacyAddressIndex> for ChildIndex {
    fn from(id: LegacyAddressIndex) -> Self {
        // Account IDs are always hardened in derivation paths.
        ChildIndex::hardened(id.0)
    }
}

/// An enumeration of the address derivation algorithm variants used by `zcashd`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ZcashdHdDerivation {
    /// A unified account derived according to ZIP 32.
    Zip32 { account_id: AccountId },
    /// The address was derived under a nonstandard path of the form:
    ///
    /// `m/32'/<coin_type>'/0x7FFFFFFF'/<address_index>'
    Post470LegacySapling { address_index: LegacyAddressIndex },
}

/// Errors that can occur in parsing the string representation of an HD key path.
#[derive(Debug)]
pub enum PathParseError {
    /// The string did not match the format of the subset of HD derivation paths that are produced
    /// by zcashd.
    PathInvalid,
    /// The coin type component of the HD derivation path did match a supported zcashd coin type.
    CoinTypeInvalid(String),
    /// The coin type component of the HD derivation did not match the coin type for the specified
    /// network.
    CoinTypeMismatch { expected: u32, actual: u32 },
    /// The account index component of the HD derivation path could not be parsed as a value in the
    /// range of a `u32`.
    AccountIndexInvalid(String),
    /// The account index component of the HD derivation path is not in the range of valid ZIP 32
    /// account indices.
    AccountIdInvalid(u32),
    /// The derivation path did not contain an address index component.
    AddressIndexMissing,
    /// The address index component of the HD derivation path could not be parsed as a value in the
    /// range of valid ZIP 32 address indices.
    AddressIndexInvalid(String),
}

impl ZcashdHdDerivation {
    const ZCASHD_LEGACY_ACCOUNT_INDEX: u32 = 0x7FFFFFFF;

    // Parses a HD key path to obtain the coin type and account ID or legacy Sapling address index.
    //
    // Historically, each key generated via the `z_getnewaddress` RPC method was treated as a separate
    // pool of funds, much like a ZIP 32 account. After the introduction of BIP 39 mnemonic seed
    // phrases in Zcashd v4.7.0, we wanted to retain these semantics but did not want `z_getnewaddress`
    // to implicitly create a new ZIP 32 account. Instead, we used a fixed keypath scheme of
    //
    // `m/32'/coin_type'/0x7FFFFFFF'/addressIndex'`
    //
    // for each new address. This is not a "standard" path, but instead is a predictable location for
    // legacy zcashd-derived keys that is minimally different from the UA account path, while unlikely
    // to collide with normal UA account usage.
    //
    // For post v4.7.0 Zcashd accounts, we use standard ZIP 32 HD derivation from the master key to
    // obtain the unified spending key.
    pub fn parse_hd_path<C: NetworkConstants>(
        network: &C,
        path: &str,
    ) -> Result<Self, PathParseError> {
        let re = Regex::new(r"^m/32'/(\d+)'/(\d+)'(?:/(\d+)')?$").expect("checked to be valid");
        let parts = re.captures(path).ok_or(PathParseError::PathInvalid)?;
        assert!(parts.len() <= 4);

        let coin_type = parts
            .get(1)
            .map_or(Err(PathParseError::PathInvalid), |part| {
                let part_str = part.as_str();
                part_str
                    .parse::<u32>()
                    .map_err(|_| PathParseError::CoinTypeInvalid(part_str.to_string()))
            })?;
        if coin_type != network.coin_type() {
            return Err(PathParseError::CoinTypeMismatch {
                expected: network.coin_type(),
                actual: coin_type,
            });
        }

        let account_index = parts
            .get(2)
            .map_or(Err(PathParseError::PathInvalid), |part| {
                let part_str = part.as_str();
                part_str
                    .parse::<u32>()
                    .map_err(|_| PathParseError::AccountIndexInvalid(part_str.to_string()))
            })?;

        if account_index == Self::ZCASHD_LEGACY_ACCOUNT_INDEX {
            let address_index =
                parts
                    .get(3)
                    .map_or(Err(PathParseError::AddressIndexMissing), |part| {
                        let part_str = part.as_str();

                        match part_str.parse::<u32>() {
                            Ok(v) if v < (1 << 31) => Ok(LegacyAddressIndex(v)),
                            _ => Err(PathParseError::AddressIndexInvalid(part_str.to_string())),
                        }
                    })?;

            Ok(ZcashdHdDerivation::Post470LegacySapling { address_index })
        } else {
            if parts.get(3).is_some() {
                return Err(PathParseError::PathInvalid);
            }
            let account_id = AccountId::try_from(account_index)
                .map_err(|_| PathParseError::AccountIdInvalid(account_index))?;
            Ok(ZcashdHdDerivation::Zip32 { account_id })
        }
    }
}

#[cfg(test)]
mod tests {
    use assert_matches::assert_matches;

    use zcash_protocol::consensus::{NetworkConstants, NetworkType};
    use zip32::AccountId;

    use super::{PathParseError, ZcashdHdDerivation, derive_mnemonic};

    #[test]
    fn derive_mnemonic_bip39_vectors() {
        use secrecy::SecretVec;

        // 256-bit entropy vectors from the reference BIP 39 English test set.
        let vectors: [([u8; 32], &str, &str); 3] = [
            (
                [0x00; 32],
                "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon art",
                "bda85446c68413707090a52022edd26a1c9462295029f2e60cd7c4f2bbd3097170af7a4d73245cafa9c3cca8d561a7c3de6f5d4a10be8ed2a5e608d68f92fcc8",
            ),
            (
                [0x80; 32],
                "letter advice cage absurd amount doctor acoustic avoid letter advice cage absurd amount doctor acoustic avoid letter advice cage absurd amount doctor acoustic bless",
                "c0c519bd0e91a2ed54357d9d1ebef6f5af218a153624cf4f2da911a0ed8f7a09e2ef61af0aca007096df430022f7a2b6fb91661a9589097069720d015e4e982f",
            ),
            (
                [0xff; 32],
                "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo vote",
                "dd48c104698c30cfe2b6142103248622fb7bb0ff692eebb00089b32d22484e1613912f0a5b694407be899ffd31ed3992c456cdf60f5d4564b8ba3f05a69890ad",
            ),
        ];

        for (entropy, phrase, seed) in vectors {
            let mnemonic = derive_mnemonic(&SecretVec::new(entropy.to_vec())).unwrap();
            assert_eq!(mnemonic.phrase(), phrase);
            assert_eq!(mnemonic.entropy(), &entropy[..]);
            assert_eq!(hex::encode(mnemonic.to_seed("TREZOR")), seed);
        }

        // Only 32-byte legacy seeds are accepted.
        assert!(derive_mnemonic(&SecretVec::new(vec![0; 16])).is_none());
        assert!(derive_mnemonic(&SecretVec::new(vec![0; 33])).is_none());
    }

    #[test]
    fn parse_zcashd_hd_path() {
        let zip32_bip39_path = format!("m/32'/{}'/0'", NetworkType::Main.coin_type());
        assert_matches!(
            ZcashdHdDerivation::parse_hd_path(&NetworkType::Main, &zip32_bip39_path),
            Ok(ZcashdHdDerivation::Zip32 {
                account_id: id
            })
            if id == AccountId::ZERO
        );

        let zip32_bip39_path_coin_invalid = format!("m/32'/{}'/0'", u64::MAX);
        assert_matches!(
            ZcashdHdDerivation::parse_hd_path(&NetworkType::Main, &zip32_bip39_path_coin_invalid),
            Err(PathParseError::CoinTypeInvalid(_))
        );

        let zip32_bip39_path_coin_mismatch = format!("m/32'/{}'/0'", NetworkType::Test.coin_type());
        assert_matches!(
            ZcashdHdDerivation::parse_hd_path(&NetworkType::Main, &zip32_bip39_path_coin_mismatch),
            Err(PathParseError::CoinTypeMismatch { .. })
        );

        let zip32_bip39_account_idx_invalid =
            format!("m/32'/{}'/{}'/0'", NetworkType::Main.coin_type(), u64::MAX);
        assert_matches!(
            ZcashdHdDerivation::parse_hd_path(&NetworkType::Main, &zip32_bip39_account_idx_invalid),
            Err(PathParseError::AccountIndexInvalid(_))
        );

        let zip32_bip39_account_id_invalid = format!(
            "m/32'/{}'/{}'",
            NetworkType::Main.coin_type(),
            ZcashdHdDerivation::ZCASHD_LEGACY_ACCOUNT_INDEX + 1
        );
        assert_matches!(
            ZcashdHdDerivation::parse_hd_path(&NetworkType::Main, &zip32_bip39_account_id_invalid),
            Err(PathParseError::AccountIdInvalid(_))
        );

        let zcashd_legacy_path = format!(
            "m/32'/{}'/{}'/0'",
            NetworkType::Main.coin_type(),
            ZcashdHdDerivation::ZCASHD_LEGACY_ACCOUNT_INDEX
        );
        assert_matches!(
            ZcashdHdDerivation::parse_hd_path(&NetworkType::Main, &zcashd_legacy_path),
            Ok(ZcashdHdDerivation::Post470LegacySapling {
                address_index
            })
            if address_index.0 == 0
        );

        let too_long_path = format!("m/32'/{}'/1'/0'", NetworkType::Main.coin_type(),);
        assert_matches!(
            ZcashdHdDerivation::parse_hd_path(&NetworkType::Main, &too_long_path),
            Err(PathParseError::PathInvalid)
        );
    }
}
