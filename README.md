# Uber 3 Major Cities Incentive Automation

This module automates the extraction and consolidation of Uber Vehicle Incentive / Promotion data specifically for the 3 primary operating fleet entities under India Master:

1. **Bangalore (BLR)**: `SAMVREEDDHI MOBILITY Pvt. Ltd. BLR P`
2. **Mumbai (MUM)**: `Samvreeddhi Mobility Pvt. Ltd. MUM P`
3. **Hyderabad (HYD)**: `Samvreeddhi Mobility Pvt Ltd HYD P`

---

## 1. Features

- **Humanized Anti-Bot Browser**: Suppresses automation flags, injects realistic hardware/GPU fingerprints, and uses human typing/mouse trajectories.
- **Permanent Cookie Persistence**: Automatically caches cookies in `cookies.json` and `storage_state.json` to bypass login and 2FA on every run.
- **Automatic 3-City Account Switching**: Automatically switches between Bangalore, Mumbai, and Hyderabad in the Uber Supplier portal.
- **Individual City & Consolidated Master Reports**:
  - `YYYYMMDD-vehicle_incentives-SAMVREEDDHI_Mobility_Pvt_Ltd_BLR_P.xlsx`
  - `YYYYMMDD-vehicle_incentives-SAMVREEDDHI_Mobility_Pvt_Ltd_MUM_P.xlsx`
  - `YYYYMMDD-vehicle_incentives-SAMVREEDDHI_Mobility_Pvt_Ltd_HYD_P.xlsx`
  - `YYYYMMDD-vehicle_incentives-SAMVREEDDHI_ALL_3_CITIES.xlsx` (Consolidated)

---

## 2. Running in PowerShell

```powershell
cd C:\Users\anura\.gemini\antigravity\scratch\letzryd-uber-incentives
python run_uber.py
```

All generated files are saved into:
`C:\Users\anura\.gemini\antigravity\scratch\letzryd-uber-incentives\uber_reports\`
