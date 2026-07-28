[![GitHub Release](https://img.shields.io/github/v/release/EiS94/db_info)](https://github.com/EiS94/db_info/releases/latest)
[![License](https://img.shields.io/github/license/EiS94/db_info)](LICENSE)
[![Stars](https://img.shields.io/github/stars/EiS94/db_info)](https://github.com/EiS94/db_info/stargazers)
[![Validate](https://img.shields.io/github/actions/workflow/status/EiS94/db_info/validate.yml?label=Validate)](https://github.com/EiS94/db_info/actions/workflows/validate.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![Usage](https://img.shields.io/badge/dynamic/json?logo=home-assistant&logoColor=ccc&label=Usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.db_info.total)](https://github.com/EiS94/db_info/releases)

## 🚉 DB Info – Public Transport with Real-Time Data

### 📌 What is DB Info?

This Home Assistant integration provides **five sensors per entry**, each showing the **upcoming public transport connections** between two locations – including **real-time updates**.

For example, you can get connections that you often need (e.g., home → main station) as a sensor, but you can also always see dynamic connections (e.g., route from my current location to home).

<img src="https://raw.githubusercontent.com/EiS94/db_info/main/images/db-info-card.gif" alt="DB Info Card Preview" width="500"/>

> Covers public transport connections across Germany – regional and long-distance.

---

### 🔀 How connections are found

Instead of relying on a single API, DB Info queries **several public transport data sources in parallel** for every request:

Four regional EFA instances, automatically restricted to the ones actually covering the requested route

Out of the box, no extra setup is required — the four EFA sources work immediately after installation. Whichever source responds with a usable connection wins, preferring **real-time data** first and the **shortest travel time** second. If a source is unavailable or blocked, the others take over automatically — you won't notice unless you check the `Source` attribute on a sensor, which always shows which backend served that particular connection.

---

### ⚙️ Setup & Usage

You can use the following as both **origin** and **destination**:

- 🧍 **Person entities** (with coordinates as an attribute)  
- 📍 **Zones**

This allows you, for example, to retrieve real-time data from a **user's current location** to their **home address**.

<img src="https://raw.githubusercontent.com/EiS94/db_info/main/images/sensor_example.png" alt="Sensor Example" width="300"/>


---

### 📊 Lovelace

#### ✅ Recommended: DB Info Card

The easiest and most feature-rich way to display your connections is the dedicated [**DB Info Card**](https://github.com/EiS94/db-info-card) — a custom Lovelace card built specifically for this integration.

<img src="https://raw.githubusercontent.com/EiS94/db_info/main/images/db-info-card.gif" alt="DB Info Card Preview" width="500"/>

**Features:**
- Clean table view with real-time delay visualization
- Expandable rows with per-segment details (stops, platforms, delays)
- Built-in visual editor — no YAML required

👉 **[Installation & Documentation](https://github.com/EiS94/db-info-card)**

---

<details>
<summary>⚙️ Alternative: flex-table-card (old method)</summary>

To display the sensors using flex-table-card, make sure the following custom cards are installed:

- [**flex-table-card**](https://github.com/custom-cards/flex-table-card)
- [**card-mod**](https://github.com/thomasloven/lovelace-card-mod)

<img src="https://raw.githubusercontent.com/EiS94/db_info/main/images/table_example.png" alt="Flex Table Card Preview" width="500"/>


```yaml
type: custom:flex-table-card
entities:
  include: sensor.<NAME_OF_SENSORS_WITH_WILDCARD>* # e.g. sensor.wu_hbf_max_morlock_stadion_verbindung_*
sort_by: sort_time
columns:
  - name: Start
    data: Departure
  - name: Verbindung
    data: Name
  - name: Abfahrt
    multi:
      - - attr
        - Departure Time
      - - attr
        - Departure Time Real
    modify: >
      var time = new Date(x.split(" ")[0]); var timeReal = new Date(x.split(
      " ")[1]); if (isNaN(timeReal.getTime())) {
        time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'});
      } else if (time >= timeReal) {
        '<div style="color:green">' +
        time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) +
        '</div>';
      } else {
        var delayMinutes = (timeReal - time) / (1000 * 60);
        if (delayMinutes > 4) {
          '<s><div style="color:grey">' +
          time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) +
          '</div></s><div style="color:red">' +
          timeReal.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) +
          '</div>';
        } else {
          '<s><div style="color:grey">' +
          time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) +
          '</div></s><div style="color:green">' +
          timeReal.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) +
          '</div>';
        }
      }
  - name: Ankunft
    multi:
      - - attr
        - Arrival Time
      - - attr
        - Arrival Time Real
    modify: >
      var time = new Date(x.split(" ")[0]); var timeReal = new Date(x.split(
      " ")[1]); if (isNaN(timeReal.getTime())) {
        time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'});
      } else if (time >= timeReal) {
        '<div style="color:green">' +
        time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) +
        '</div>';
      } else {
        var delayMinutes = (timeReal - time) / (1000 * 60);
        if (delayMinutes > 4) {
          '<s><div style="color:grey">' +
          time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) +
          '</div></s><div style="color:red">' +
          timeReal.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) +
          '</div>';
        } else {
          '<s><div style="color:grey">' +
          time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) +
          '</div></s><div style="color:green">' +
          timeReal.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) +
          '</div>';
        }
      }
  - name: sort_time
    multi:
      - - attr
        - Departure Time
      - - attr
        - Departure Time Real
    modify: >
      var time = new Date(x.split(" ")[0]); var timeReal = new Date(x.split(
      " ")[1]); if (isNaN(timeReal.getTime())) {
        time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'});
      } else {
        '<div style="color:green">' +
        timeReal.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) +
        '</div>';
      }
    hidden: true
css:
  table+: "padding: 1px 5px 16px 5px;"
card_mod:
  style:
    $: |
      h1.card-header {
        font-size: 20px;
        padding-top: 3px;
        padding-bottom: 1px; 
      }
```

</details>

---

### 🛠️ Services

DB Info provides one action, registered globally (not per entry):

| Service | Description |
|---|---|
| `db_info.refresh_all` | Manually refreshes **all** DB Info entries at once, instead of waiting for their individual update intervals. Useful for e.g. an automation right before you leave the house. |

Call it under **Developer Tools → Actions**, search for "Refresh all connections", or from YAML:

```yaml
action: db_info.refresh_all
```

---

### 📥 Installation

#### 🔹Via [HACS](https://hacs.xyz/) 
<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=EiS94&repository=db_info&category=integration" target="_blank"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open the DB Info Repository inside the Home Assistant Community Store." /></a>

#### 🔹 Manual Installation
Copy the folder: `custom_components/db_info` into your Home Assistant directory: `config/custom_components`

---

### 🗑️ Removal

1. Go to **Settings → Devices & Services → DB Info**, open each entry and remove it (this also removes its sensors, button, switch and datetime entity).
2. If installed via HACS, remove it there too: **HACS → Integrations → DB Info → ⋮ → Remove**.
3. If installed manually, delete the `custom_components/db_info` folder from your Home Assistant config directory.
4. Restart Home Assistant.

---

Enjoy using the integration! 🚆

<a href="https://www.buymeacoffee.com/eis94" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>