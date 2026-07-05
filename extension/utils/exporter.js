// LeadList - Export Utility
window.LeadListExporter = {
  toCSV(leads) {
    const headers = ['Name', 'Title', 'Company', 'Location', 'Email(s)', 'Phone(s)', 'LinkedIn URL', 'Scraped At'];
    const rows = leads.map(l => [
      l.name || '',
      l.title || '',
      l.company || '',
      l.location || '',
      (l.emails || []).join(' | '),
      (l.phones || []).join(' | '),
      l.profileUrl || '',
      l.scrapedAt ? new Date(l.scrapedAt).toLocaleString() : ''
    ]);
    const escape = v => `"${String(v).replace(/"/g, '""')}"`;
    return [headers.map(escape).join(','), ...rows.map(r => r.map(escape).join(','))].join('\n');
  },

  downloadCSV(leads, filename = 'leadlist_export.csv') {
    const csv = this.toCSV(leads);
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  toJSON(leads) {
    return JSON.stringify(leads, null, 2);
  },

  downloadJSON(leads, filename = 'leadlist_export.json') {
    const blob = new Blob([this.toJSON(leads)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  copyToClipboard(leads) {
    const text = leads.map(l =>
      `${l.name} | ${l.title} | ${l.company} | ${(l.emails||[]).join(', ')} | ${(l.phones||[]).join(', ')} | ${l.profileUrl}`
    ).join('\n');
    navigator.clipboard.writeText(text).catch(() => {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    });
    return text;
  }
};
