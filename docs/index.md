---
layout: default
title: 📅 Fizjo-Plan
---

# 📅 Fizjo-Plan

Welcome! This page automatically lists all available `.ics` schedule feeds in this site.

## Available Calendars

{% for file in site.static_files %}
{% if file.path contains '/docs/' and file.extname == '.ics' %}

- [{{ file.name }}]({{ file.name }})
  {% endif %}
  {% endfor %}

---

### 🔗 How to Subscribe

- **Google Calendar**

  1. Open [Google Calendar](https://calendar.google.com/).
  2. In the left panel, click **+** → _From URL_.
  3. Paste the `.ics` link above.

- **Apple Calendar**
  1. Open the Calendar app.
  2. Go to File → _New Calendar Subscription_.
  3. Paste the `.ics` link above.

---

ℹ️ These feeds update automatically whenever the underlying schedule changes.
