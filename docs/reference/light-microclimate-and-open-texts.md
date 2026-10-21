# Light, shading, patio microclimate, feeding, and open texts

Background sources we may embed, and four methods the twin needs: converting weather
radiation to plant light, correcting for patio shade, correcting forecast temperature for
an urban garden, and how long compost feeds a pot. Swept 3 Oct 2026 by direct fetch,
CrossRef and Europe PMC. "Verified" means the licence or number was read on the page or in
API metadata; UNVERIFIED items come from memory.

## 1. Open textbooks and manuals

| Title | Publisher and link | Licence | What matters |
|---|---|---|---|
| **Rain or Shine** (Ochsner; author UNVERIFIED) | Oklahoma State, open.library.okstate.edu/rainorshine/ | **CC BY 4.0** (verified) | ch. 3 soil water content and potential; ch. 10 evaporation; ch. 11 transpiration and root water uptake; ch. 12 surface energy balance and reference ET; ch. 13 soil temperature. **Best embeddable text for the twin.** |
| **The Science of Plants** | Univ. of Minnesota, open.lib.umn.edu/horticulture/ | CC BY-NC 4.0 (verified, NC) | ch. 11 water and light; ch. 12 soils, fertility and plant growth; ch. 3 leaves, shoots, roots |
| Introduction to Soil Science (Anderson) | Iowa State, iastate.pressbooks.pub/introsoilscience/ | CC BY 4.0 (verified) | soil water and fertility |
| Soil and Water Conservation: an annotated bibliography | Kansas State, kstatelibraries.pressbooks.pub/soilandwater/ | CC BY 4.0 (verified) | background |
| Botany (Ha, Morrow, Algiers) | LibreTexts | CC BY-NC 4.0 on the book page; check each page | water transport, nutrition, stress |
| Biology 2e | OpenStax | CC BY 4.0 (UNVERIFIED, page JS-rendered) | plant form, physiology, soil nutrition |
| FAO-56 Crop Evapotranspiration | fao.org/4/x0490e/x0490e00.htm | **not open**: all rights reserved; non-commercial reuse with acknowledgement | implement the equations and cite; never embed the text |
| NC Extension Gardener Handbook | content.ces.ncsu.edu/extension-gardener-handbook | no CC statement; treat as all rights reserved | ch. 18 Plants Grown in Containers; cite only |
| USDA herb leaflets: Savory herbs in the garden (1940), Growing culinary herbs (1938), Seasoning herbs for indoor growing (1935) | archive.org/details/savoryherbsingar1940unit, /growingculinaryh222unit, /seasoningherbsfo1935unit | US federal works, public domain (item statements not checked) | dated, but the only public-domain herb guides found |

Not found: a CC-licensed master gardener handbook, or a modern USDA container-gardening
publication.

## 2. Converting weather radiation to plant light

**Formula to implement.** DLI (mol m⁻² d⁻¹) = Rs (MJ m⁻² d⁻¹) × 0.45 × 4.48 = **2.02 × Rs**,
following Faust and Logan 2018, HortScience 53(9), doi:10.21273/HORTSCI13144-18, whose
abstract converts global horizontal irradiance at 0.007265 mol per Wh (45% PAR, 4.48 µmol
per J). Upper bound with 0.50 and 4.57 is 2.29 × Rs. PPFD in µmol m⁻² s⁻¹ × 0.0864 = DLI.

| Item | Source | Note |
|---|---|---|
| 4.57 µmol per J for daylight PAR | Thimijan and Heins 1983, HortScience 18:818, doi:10.21273/HORTSCI.18.6.818 (CC BY-NC-ND) | figure itself not read (UNVERIFIED) |
| PAR definition | McCree 1972, Agric Meteorol 9:191 | closed |
| PAR fraction 0.45 to 0.50 | no open primary source located | use 0.45 |
| **DLI classes** | Purdue HO-238-W (Torres and Lopez), extension.purdue.edu/extmedia/ho/ho-238-w.pdf, cite only | **3 to 6 low, 6 to 12 medium, 12 to 18 high, above 18 very high**; outdoor DLI runs 5 to 30 |
| Herb DLI response | Walters, Tarr, Lopez 2023, PLOS ONE, doi:10.1371/journal.pone.0294905 (CC BY) | basil, sage, spearmint across DLI 5 to 19; numbers in `herb-growth-facts.md` |
| Tree crown transmission | Konarska et al. 2013, Theor Appl Climatol, doi:10.1007/s00704-013-1000-3 (closed) | a few percent in leaf, roughly 40 to 50% leafless (UNVERIFIED) |

No published transmission factor for north-facing walls exists; compute it from geometry.

## 3. Shading and sun path for a patio

**Simplest defensible correction.** Take hourly direct and diffuse shortwave from the
weather API. Zero the direct part in hours when the sun is below the horizon profile for
that azimuth. Multiply the diffuse part by the sky view factor. Sum over the day and apply
2.02. Tree-covered sectors need a transmissivity rather than zero.

| Tool or method | Source | Licence | Note |
|---|---|---|---|
| pvlib horizon shading example | pvlib-python.readthedocs.io, gallery/shading | BSD-3 (UNVERIFIED) | interpolate a horizon elevation profile by azimuth; zero direct beam below it; diffuse untouched |
| UMEP | umep-docs.readthedocs.io; Lindberg et al. 2018, doi:10.1016/j.envsoft.2017.09.020 | paper CC BY-NC-ND; tool GPL (UNVERIFIED) | sky view factor and shadow casting from a surface model; heavy, QGIS-based |
| GRASS r.sun | grass.osgeo.org | GPL (UNVERIFIED) | irradiance on a raster with horizon shadowing |
| Environment Agency National LiDAR Programme | data.gov.uk/dataset/f0db0249-f17b-4036-9e65-309148c97ce4 | OGL v3 (UNVERIFIED on that page) | 1 m surface model for all England incl. trees and building edges |
| **Phone fisheye shading factor** | Oliveira Panão et al. 2019, Solar Energy, doi:10.1016/j.solener.2019.08.047 | closed | closest match to "horizon profile from a phone photo" |
| Sky view factor from a spherical camera | Honjo et al. 2019, J Agric Meteorol, doi:10.2480/agrmet.D-18-00027 | free on J-STAGE | |
| Hemispherical photos from phone panoramas | Arietta 2021, Forestry, doi:10.1093/forestry/cpab034; preprint doi:10.1101/2020.12.15.422956 | preprint CC BY-NC-ND | |
| Phone hemispherical photography for canopy structure | Díaz et al., preprint doi:10.1101/2021.03.17.435793 | CC BY-NC-ND | |

For v1 the horizon profile can be a hand-entered table of elevation by compass sector
(eight numbers), which keeps the phone-panorama method as a later module.

## 4. Urban garden microclimate

| Source | Licence | Finding |
|---|---|---|
| **Coney et al. 2022, Meteorological Applications, doi:10.1002/met.2075** | CC BY 4.0 | UK-wide Netatmo: sensor accurate to 0.3 °C in the lab, response time constant 12.7 min, **warm bias above 1 °C against Met Office stations**, reduced by quality control. Best UK source. |
| Chapman, Bell, Bell 2017, Int J Climatol, doi:10.1002/joc.4940 | Wiley | London summer 2015 Netatmo: **urban heat island of 1 to 6 °C depending on stability**; warm bias from non-standard siting |
| Napoly et al. 2018, CrowdQC, Front Earth Sci, doi:10.3389/feart.2018.00118 | CC BY 4.0 | statistical quality control needing no reference stations |
| Fenner et al. 2021, CrowdQC+, Front Environ Sci, doi:10.3389/fenvs.2021.720747 | CC BY 4.0 | adds a radiation-error check and a sensor-lag correction |
| Meier et al. 2017, Urban Climate, doi:10.1016/j.uclim.2017.01.006 | closed | Berlin crowdsourced temperatures |

Not found: a quantified source for wall heat storage raising night minima, or for wind
sheltering reducing ET on a patio. The defensible route is a sensitivity run of the
Penman-Monteith equation with reduced wind speed, reported as a range.

Combined with `risk-models.md` section 5: the forecast grid minimum for a sheltered London
patio is biased cold by 1 to 2 °C on average and by up to 6 °C on clear calm nights, while
exposed grass-level surfaces run 2 to 4 °C colder than screen level on the same nights. The
two effects oppose each other, which is why the frost rule carries a band, not a number.

## 5. Compost and feeding

- **The "feeds for 4 to 6 weeks" claim was not sourced.** The RHS pages that loaded do not state it.
- NC Extension Gardener Handbook ch. 18 (cite only): starter fertiliser in commercial potting mixes lasts **"only a couple of weeks"**; then liquid feed weekly at half strength or fortnightly at full strength. Over-feeding sign: a white salt crust on the mix; remedy is leaching with water for several minutes.
- RHS Container maintenance (cite only): edibles and hungry plants get liquid feed from April to the end of August; feed onto moist compost; soil-less composts need trace elements.
- RHS Growing herbs in containers (cite only): a balanced rather than potassium-rich feed for leafy growth; mint wants moist fertile soil and frequent replanting; loam-based compost with grit is mentioned (which herbs it applies to was truncated).
- Hungry (basil, mint, parsley) vs lean (sage, thyme, rosemary): consistent with RHS, no open-licence quantitative source found. Lead: an Iowa State thesis on fertiliser for containerised culinary herbs (doi:10.31274/td-20251215-249), not read.
- Consequence for advice: **no feeding recommendation between September and March**, and "feed" is never the first suggestion for a yellowing plant in autumn.

## Takeaways

1. Embed from Rain or Shine (CC BY) for soil water and ET background; use The Science of Plants (NC) only while the project stays non-commercial.
2. Implement DLI = 2.02 × Rs and classify with the Purdue bands.
3. Start shading as eight hand-entered horizon elevations; zero direct beam below them, scale diffuse by sky view factor.
4. Carry a temperature bias band for the patio rather than a correction; cite Coney 2022 and Chapman 2017.
5. Treat feeding as seasonal and low-confidence; no source supports a fixed compost-feeds-for-N-weeks rule.
