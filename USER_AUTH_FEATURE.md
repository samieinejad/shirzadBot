# Multi-User Authentication System

## Overview
Adding comprehensive multi-user authentication system with:
- Iranian mobile phone verification (OTP)
- User profiles with token management
- Payping billing integration
- Friendly UX for all features

## Implementation Plan

### 1. Database Schema
Add these tables to existing `init_db()`:
- `users` - User accounts
- `user_otp_codes` - OTP verification codes
- `user_billing` - Billing history
- `user_tokens` - User-specific bot tokens

### 2. SMS Provider Options
For Iranian mobile verification, you need to choose:
- **Kavenegar** (Iranian SMS service)
- **Ghasedak** (Iranian SMS service)  
- **Melipayamak** (Iranian SMS service)
- **SMS.ir** (Iranian SMS service)

### 3. Payping Integration
- API: https://payping.io/
- Need: Merchant Token from Payping dashboard
- Flow: Charge → Redirect → Verify → Update balance

### 4. UI Changes
- Add login/signup page
- Protect all routes with authentication
- Per-user dashboard
- Billing page with Payping
- Profile settings with token management

## Questions for You:

1. **SMS Provider**: Which service do you want to use? (Kavenegar recommended)
2. **Pricing**: What's your pricing model? (per month, per broadcast, etc.)
3. **Payping**: Do you have a merchant account?
4. **Default Balance**: Starting balance for new users?

## Next Steps

Once you answer these, I'll implement:
1. Database migration
2. SMS OTP system
3. User authentication middleware
4. Payping integration
5. New UI pages
6. Token migration per user

