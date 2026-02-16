---
layout: default
title: 📅 Fizjo-Plan
---

# 📅 Fizjo-Plan

**Automated physiotherapy schedules for AWF Poznań students**

Subscribe to your personalized class calendar below. Updates automatically daily.

## Available Calendars

{% for file in site.static_files %}
{% if file.extname == '.ics' and file.name != 'iwonka.ics' and file.name != 'ola.ics' and file.name != 'gracjana.ics' %}
- [{{ file.name }}]({{ file.name }})
{% endif %}
{% endfor %}

## 🔗 How to Subscribe

**Google Calendar**: Settings → Add calendar → From URL → Paste link above

**Apple Calendar**: File → New Calendar Subscription → Paste link above

**Outlook**: Add calendar → Subscribe from web → Paste link above

---

ℹ️ These feeds update automatically whenever the underlying schedule changes.
