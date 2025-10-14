## 🚉 DB_Info – Public Transport with Real-Time Data

### 📌 What is DB_Info?

This integration provides **five sensors per entry**, each showing the **upcoming public transport connections** between two locations – including **real-time updates**.  

<img src="https://github.com/EiS94/db_info/raw/main/images/table_example.png" alt="Table Example" width="400"/>

> Note: It works **exclusively within the Deutsche Bahn (DB) network**.


---

### ⚙️ Setup & Usage

You can use the following as both **origin** and **destination**:

- 🧍 **Person entities** (with coordinates as an attribute)  
- 📍 **Zones**

This allows you, for example, to retrieve real-time data from a **user’s current location** to their **home address**.

<img src="https://github.com/EiS94/db_info/raw/main/images/sensor_example.png" alt="Sensor Example" width="300"/>

---

### 📊 Lovelace Example

To display the sensors in a clean table view, you can use a custom Lovelace setup.

#### ✅ Requirements

Make sure the following custom cards are installed:

- [**flex-table-card**](https://github.com/custom-cards/flex-table-card)  
- [**card-mod**](https://github.com/thomasloven/lovelace-card-mod)

#### 🖼️ Code

<img src="https://github.com/EiS94/db_info/raw/main/images/table_example.png" alt="Table Example" width="400"/>

```yaml
type: custom:flex-table-card
entities:
  include: sensor.<NAME_OF_SENSORS_WITH_WILDCARD>* # e.g. sensor.wu_hbf_max_morlock_stadion_verbindung_*
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
      var time = new Date(x.split(" ")[0]); var timeReal = new Date(x.split("
      ")[1]); if (isNaN(timeReal.getTime())) {
        time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'});
      } else if (time >= timeReal) {
        '<div style="color:green">' + time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) + '</div>';
      } else {
        var delayMinutes = (timeReal - time) / (1000 * 60);
        if (delayMinutes > 10) {
          '<s><div style="color:grey">' + time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) + '</div></s>' +
          '<div style="color:red">' + timeReal.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) + '</div>';
        } else {
          '<s><div style="color:grey">' + time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) + '</div></s>' +
          '<div style="color:green">' + timeReal.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) + '</div>';
        }
      }
  - name: Ankunft
    multi:
      - - attr
        - Arrival Time
      - - attr
        - Arrival Time Real
    modify: >
      var time = new Date(x.split(" ")[0]); var timeReal = new Date(x.split("
      ")[1]); if (isNaN(timeReal.getTime())) {
        time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'});
      } else if (time >= timeReal) {
        '<div style="color:green">' + time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) + '</div>';
      } else {
        var delayMinutes = (timeReal - time) / (1000 * 60);
        if (delayMinutes > 10) {
          '<s><div style="color:grey">' + time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) + '</div></s>' +
          '<div style="color:red">' + timeReal.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) + '</div>';
        } else {
          '<s><div style="color:grey">' + time.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) + '</div></s>' +
          '<div style="color:green">' + timeReal.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'}) + '</div>';
        }
      }
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

---

### 📥 Installation

#### 🔹 Manual Installation
Copy the folder: `custom_components/db_info` into your Home Assistant directory: `config/custom_components`


#### 🔹 HACS
Currently **not available via HACS**.

---

### 🔧 In Development

Future updates will allow **manually entering coordinates** as origin or destination, giving you more flexibility beyond person or zone entities.

---

Enjoy using the integration! 🚆

<a href="https://www.buymeacoffee.com/eis94" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>
