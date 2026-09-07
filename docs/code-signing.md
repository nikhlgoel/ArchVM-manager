# Code signing

Unsigned, `ArchVM.exe` triggers **Windows SmartScreen** — the blue "Windows
protected your PC" screen, where running the app takes two extra clicks behind
*More info → Run anyway*. Signing removes the "Unknown publisher" label and
replaces it with your verified name.

Signing does **not** by itself remove the SmartScreen warning. That needs
*reputation*, which a new certificate has to earn — except with EV, which is
trusted immediately.

---

## The options

| Route | Cost | Removes "unknown publisher" | Instant SmartScreen trust | Hardware token |
|---|---|---|---|---|
| Unsigned | free | no | no | — |
| Self-signed | free | only on machines that installed your cert | no | no |
| **Azure Trusted Signing** | **~$10/month** | yes | no — earns reputation | no |
| OV certificate | ~$200–400/yr | yes | no — earns reputation | **yes** |
| EV certificate | ~$400–700/yr | yes | **yes** | **yes** |

### Recommended for this project: Azure Trusted Signing

Microsoft's own service, and the only cheap route since the rules changed.

- No hardware token — Microsoft holds the key in an HSM, you sign via API.
- **Individual developers are eligible**, not just companies. Microsoft asks for
  a verifiable identity history (roughly three years); a long-standing personal
  legal identity normally satisfies it.
- Certificates are short-lived and reissued automatically.
- Integrates with `signtool` and GitHub Actions.

Sign-up: Azure Portal → *Trusted Signing Accounts* → create an account, add an
Identity Validation request, wait for approval (days, not weeks), then create a
Certificate Profile.

### Why OV and EV now need a USB token

Since **1 June 2023**, the CA/Browser Forum requires code-signing private keys
to live on certified hardware (FIPS 140-2 Level 2 or equivalent). Every
commercial CA now ships a physical token or requires an HSM. That is what makes
traditional certificates awkward for a solo developer, and why Trusted Signing
exists.

### Self-signed: useful only for yourself

Fine for testing that the signing pipeline works, or for a machine you control.
It does nothing for anyone else — their Windows has no reason to trust your
certificate.

```powershell
# create a test certificate (developer machines only)
$cert = New-SelfSignedCertificate -Type CodeSigningCert `
  -Subject "CN=ArchVM Dev" -CertStoreLocation Cert:\CurrentUser\My
# trust it locally
Export-Certificate -Cert $cert -FilePath archvm-dev.cer
Import-Certificate -FilePath archvm-dev.cer -CertStoreLocation Cert:\CurrentUser\Root
```

---

## Signing the build

`signtool.exe` ships with the Windows SDK, usually at
`C:\Program Files (x86)\Windows Kits\10\bin\<version>\x64\signtool.exe`.

**Always timestamp.** Without a timestamp the signature dies with the
certificate; with one it stays valid for the life of the timestamp authority's
own certificate.

```powershell
signtool sign `
  /fd SHA256 `
  /tr http://timestamp.digicert.com /td SHA256 `
  /n "Your Certificate Subject Name" `
  "dist\ArchVM\ArchVM.exe"

signtool verify /pa /v "dist\ArchVM\ArchVM.exe"
```

With Azure Trusted Signing, `/n` is replaced by the dlib provider:

```powershell
signtool sign /v /debug /fd SHA256 `
  /tr http://timestamp.acs.microsoft.com /td SHA256 `
  /dlib "C:\path\to\Azure.CodeSigning.Dlib.dll" `
  /dmdf "metadata.json" `
  "dist\ArchVM\ArchVM.exe"
```

`metadata.json`:

```json
{
  "Endpoint": "https://eus.codesigning.azure.net",
  "CodeSigningAccountName": "your-account",
  "CertificateProfileName": "your-profile"
}
```

---

## Building it into this project

`app/build.py` accepts a signing identity and signs the executable after
PyInstaller finishes:

```bash
python build.py --sign "Your Certificate Subject Name"
```

It is a no-op when the flag is absent or `signtool` is missing, so unsigned
builds keep working unchanged.

---

## What signing does not do

- **It is not a security review.** It proves the file came from you and has not
  been altered. Nothing more.
- **It does not skip the first-run warning** unless the certificate is EV or has
  built reputation through download volume.
- **It does not cover the installer separately** — if you later add one, sign
  that too, and sign the payload before packaging it.

---

## Practical order

1. Ship unsigned while it is a personal project. SmartScreen is two extra
   clicks and costs nothing.
2. If you distribute it beyond yourself, get **Azure Trusted Signing** at
   ~$10/month and wire `--sign` into the build.
3. Only consider **EV** if a warning-free first run genuinely matters — that is
   the sole thing the extra few hundred a year buys.
