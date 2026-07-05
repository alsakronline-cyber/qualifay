# LeadList - Email & Phone Scraper
### A Scalelist-inspired Chrome Extension

Instantly extract verified emails and phone numbers from LinkedIn profiles, search results, and company pages — all stored locally in your browser with one-click CSV export.

---

## ✨ Features

- 🔍 **Auto-detect** LinkedIn profiles, search pages, and company pages
- 📧 **Extract emails** from visible content and the Contact Info modal
- 📞 **Extract phones** from profile pages
- 📋 **Leads manager** — save, search, filter, and delete leads
- 📤 **Export CSV / JSON** with one click
- 🎨 **Scalelist-inspired dark UI** — premium sidebar panel injected into LinkedIn
- 💾 **Local storage** — all data stays in your browser, no server needed

---

## 🚀 Installation (Load Unpacked)

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer Mode** (toggle in top-right corner)
3. Click **"Load unpacked"**
4. Select this folder: `c:\Users\pc shop\Desktop\Projects\LeadList - Email & Phone Scraper`
5. The **LeadList** extension will appear in your toolbar

---

## 🎯 How to Use

### Scraping a Profile
1. Go to any LinkedIn profile (e.g. `linkedin.com/in/someuser`)
2. Click the blue **LeadList** button floating in the bottom-right corner
3. The sidebar panel opens — click **Extract Contacts**
4. Emails and phones are extracted and saved automatically

### Scraping Search Results
1. Go to `linkedin.com/search/results/people/` and run a search
2. Open the LeadList sidebar and click **Extract Contacts**
3. All visible profiles on the page are saved to your leads list

### Managing Leads
- Switch to the **Leads tab** in the sidebar to view all saved contacts
- Use the **search bar** to filter by name, email, or company
- Click a lead row to open their LinkedIn profile
- Click the **trash icon** to delete individual leads
- Use **Export CSV** to download all leads as a spreadsheet

### Popup (toolbar icon)
- Click the LeadList icon in the Chrome toolbar for a quick stats overview
- See total leads, emails, and phones collected
- One-click **Open Scraper Panel** or **Export CSV**

---

## 📁 File Structure

```
LeadList - Email & Phone Scraper/
├── manifest.json           ← Chrome Extension config (Manifest V3)
├── background.js           ← Service worker & storage management
├── content.js              ← Injected into LinkedIn pages
├── generate_icons.js       ← Icon generator script (already run)
├── icons/
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
├── popup/
│   ├── popup.html          ← Extension toolbar popup
│   ├── popup.css
│   └── popup.js
├── sidebar/
│   ├── sidebar.html        ← Main scraper panel (injected iframe)
│   ├── sidebar.css         ← Toggle button styles (injected into LinkedIn)
│   └── sidebar.js
└── utils/
    ├── extractor.js        ← Email/phone regex extraction
    ├── storage.js          ← chrome.storage wrapper
    └── exporter.js         ← CSV/JSON download
```

---

## ⚠️ Notes & Limitations

- **LinkedIn limits**: The contact info modal (phone/email) is only shown if the profile owner has made it visible to their connections. You must be connected or the data must be publicly visible.
- **Anti-scraping**: LinkedIn may detect automated clicks. Use the tool at a normal pace.
- **No API keys needed**: Everything runs locally in your browser.
- **Permissions used**: `storage` — no data is sent to any external server.

---

## 🔧 Troubleshooting

| Issue | Fix |
|-------|-----|
| Sidebar not appearing | Refresh the LinkedIn page after installing |
| No emails found | The profile owner hasn't shared contact info, or you're not connected |
| Extension not loading | Make sure Developer Mode is ON in `chrome://extensions` |
| Icons missing | Run `node generate_icons.js` from the project folder |

---

*Built with ❤️ — Scalelist-inspired design, fully local, no subscriptions.*
