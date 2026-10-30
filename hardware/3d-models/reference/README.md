# Third-party reference material (not redistributed)

The rover models reuse geometry and documentation published by ELEGOO. Neither
official repository carries a license file, so those files are **not copied
into this repository**. This page pins the exact sources and explains how to
fetch them. Do not assign a license to this material.

## Pinned sources (inspected 2026-10-29)

| Repository | Commit inspected | License field | Relevant files |
| --- | --- | --- | --- |
| [elegooofficial/ELEGOO-Smart-Robot-Car-Kit-V4.0](https://github.com/elegooofficial/ELEGOO-Smart-Robot-Car-Kit-V4.0) | `096094e07dc7e5eea8c986986158e2d9111dab64` (2021-03-09) | none | `Smart Robot Car 3D model.zip` (stock plate STLs), `Schematic diagram.zip` (shield schematic + vendor datasheets), `SmartRobotCarV4.0_V0_20210104.zip` |
| [elegooofficial/ELEGOO-Smart-Robot-Car-Kit-V4.0-New](https://github.com/elegooofficial/ELEGOO-Smart-Robot-Car-Kit-V4.0-New) | `76d82704b20b8b38d3eb874afd865b349cbc1a48` (2026-06-08) | none | firmware and README (this repository is a fork of it) |

Git blob identifiers recorded when the Rover V3 package fetched them
(`source/rover-v3/electrical_reference/download_provenance.json`):

| File | Blob SHA | SHA-256 | Bytes |
| --- | --- | --- | --- |
| `Schematic diagram.zip` | `009062603977c70bb009713d3c8153cd21806c85` | `8e7a488c3924d1ed5ebfb5601190135ea9e8a9141ac42960d430d695d6ab4bc2` | 1763430 |
| V4.0 `README.md` | `a933a51bd9f4d5e1d5f1319124deffa7e1f56083` | `cd21d2709b6de4b4905871a5d22d368637a648e4504ce4d7a98560ed5cd0f9c2` | 66 |
| V4.0-New `README.md` | `995069bbf59dd4bc9aca08ec4f3813f656b9faf3` | `a547803cd73f58a347f61cfa4de5ce0237ebb95d199b968ddc33db0f7b244475` | 5930 |

The four PDFs inside `Schematic diagram.zip` are listed with page counts and
hashes in `source/rover-v3/electrical_reference/pdf_inventory.json`:
`SmartRobot-Shield.pdf` (ELEGOO), `DRV8835_datasheet_en.pdf` (Texas
Instruments), `ESP32-wrover_datasheet_en.pdf` (Espressif),
`ITR20001_datasheet_en.pdf`.

## How the imported models depend on these sources

* The stock chassis plates in every reference assembly (explorer v0.1, full
  body v0.2, wheelbase-76 v0.3, Rover V3 `oem_geometry.json`) were
  reconstructed from the three plate STLs in `Smart Robot Car 3D model.zip`.
  The reconstructed solids are the maintainer's own work; the dimensional
  source remains ELEGOO's.
* `source/rover-v3/electrical_reference/` keeps the harness and pin comparison
  tables and the download provenance, but not the PDFs.

## Retrieval

Pinned download of the schematic archive (any platform with `curl`):

```bash
curl -L -o Schematic_diagram.zip \
  "https://raw.githubusercontent.com/elegooofficial/ELEGOO-Smart-Robot-Car-Kit-V4.0/096094e07dc7e5eea8c986986158e2d9111dab64/Schematic%20diagram.zip"
sha256sum Schematic_diagram.zip   # expect 8e7a488c...6ab4bc2
```

Stock plate meshes:

```bash
curl -L -o Smart_Robot_Car_3D_model.zip \
  "https://raw.githubusercontent.com/elegooofficial/ELEGOO-Smart-Robot-Car-Kit-V4.0/096094e07dc7e5eea8c986986158e2d9111dab64/Smart%20Robot%20Car%203D%20model.zip"
```

The package script `source/rover-v3/recover_oem_references.py` re-downloads the
schematic archive and READMEs from the `main` branch (not pinned) and rebuilds
`download_provenance.json`; run it from a copy of `source/rover-v3/` if you
want the PDFs next to the electrical reference tables.
