#!/usr/bin/env bash
# Fetch the REAL pea creator profile page HTML + profile API using the user-provided auth.
set -e

JWT="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjdXN0b21lcl9pZCI6IkMxMzE0MjEwNzIwMjZoc21uZ1NtIiwiY3VzdG9tZXJfbmFtZSI6IndhaDE3NjM3NTE0NDjnmoTlm6LpmJ8iLCJlbWFpbCI6IndhaDE3NjM3NTE0NDhAMTYzLmNvbSIsImV4cCI6MTc4NTI4OTExNiwiZnJlc2giOmZhbHNlLCJpYXQiOjE3ODQ2ODQzMTYsImp0aSI6ImVjYjJiZTlhLTY2MjYtNDkxYy04Nzc3LTlmOWIwYjQ1NmYxNCIsIm5iZiI6MTc4NDY4NDMxNiwib3JnX2lkIjoiQzEzMTQyMTA3MjAyNmhzbW5nU20iLCJvcmdfbmFtZSI6IndhaDE3NjM3NTE0NDjnmoTlm6LpmJ8iLCJvcmdfdHlwZSI6ImluZGl2aWR1YWwiLCJwaG9uZV9udW1iZXIiOiIiLCJwaG9uZV9yZWdpb24iOiIiLCJyb2xlIjoib3duZXIiLCJzdGF0dXMiOiJhY3RpdmUiLCJzdWIiOiJ3YWgxNzYzNzUxNDQ4QDE2My5jb20iLCJ0eXBlIjoiYWNjZXNzIiwidXNlcl9pZCI6IjA4MzQ1MzMyLThhOWQtNDIwNi1iNTFkLTkzNTEwZjM4ZmU4MCIsInVzZXJfbmFtZSI6IndhaDE3NjM3NTE0NDgiLCJ1c2VyX3R5cGUiOiJvd25lciJ9.ZEKY2f_noQVpC7ewkAa1mY6WPLfSsPr1a11a9x4MjnY"

# Raw cookie as captured (contains ^ cmd-escapes); stripped below.
RAWCOOKIE='tap_tracking_id=trk_c1f033d3259b8c3189211c0e18569fda; _fbp=fb.1.1784684281560.873178707194446729.AQYCAQMB; 3bdb909c95037d16=Ar81VO4IVvOnWVCpFFf2iFAfCNarG5vq1RiZcjEf62OLARgyCMgAl6lSRNJkfSpkIhHrCtK7icEu7JMROzS9nzpp^%^2BObTfz5vSlKpFX9^%^2BushhpQfvRHnIE9Sew9FYZghJPZn2rp55Mq9R1VpBNeKQlwDimLHePQo6puIX3SvpqJrBY^%^2BiTCaRjcKVd5fmFFDtVpshoXZyxC5lFvXr0Wzz130JblrFweI^%^2Fu4QwpRtpj50kRiRdGKDKjCmi^%^2BkDUmtpfKToJwBC8d0q^%^2FwC^%^2B5I3DrQYg9bFjeVcbGdPL8qt07ATsirdFcTyY5d6w^%^3D^%^3D; _twpid=tw.1784684284434.203119461396754041; _tt_enable_cookie=1; _ttp=01KY3QJ4N07242FXQREZRFSY1Z_.tt.1; _pin_unauth=dWlkPU1XVXpZVEUzTlRjdFpUa3daQzAwTkRFMkxUa3lNakV0WXpWbU9ERmlZVEJqWWpBeg; _rdt_uuid=1784684284270.d59ee433-cab4-465a-b0b8-274a3a2fc533; tap_locale=zh; _TDID_CK=1784684288944; __stripe_mid=664f990f-c5bc-452e-a1dc-4896ec3075a4f3edeb; __stripe_sid=a6ad6ca1-4af4-4878-b0db-d89aa605a55c0ac157; g_state=^{^\^"i_l^\^":0,^\^"i_ll^\^":1784684315864,^\^"i_b^\^":^\^"YDcyMrUMsu64TmoZQyUIXz5Cw7cH74ydkO2fReR4QbU^\^",^\^"i_e^\^":^{^\^"enable_itp_optimization^\^":24^},^\^"i_et^\^":1784684315864^}; cc_cookie=^%^7B^%^22categories^%^22^%^3A^%^5B^%^22necessary^%^22^%^2C^%^22analytics^%^22^%^2C^%^22ads_measurement^%^22^%^2C^%^22ads_user_data^%^22^%^2C^%^22ads_personalization^%^22^%^5D^%^2C^%^22revision^%^22^%^3A1^%^2C^%^22data^%^22^%^3Anull^%^2C^%^22consentTimestamp^%^22^%^3A^%^222026-07-22T01^%^3A39^%^3A59.588Z^%^22^%^2C^%^22consentId^%^22^%^3A^%^22728478c8-de97-42e1-954b-ba85f760892b^%^22^%^2C^%^22services^%^22^%^3A^%^7B^%^22necessary^%^22^%^3A^%^5B^%^5D^%^2C^%^22analytics^%^22^%^3A^%^5B^%^5D^%^2C^%^22ads_measurement^%^22^%^3A^%^5B^%^5D^%^2C^%^22ads_user_data^%^22^%^3A^%^5B^%^5D^%^2C^%^22ads_personalization^%^22^%^3A^%^5B^%^5D^%^7D^%^2C^%^22languageCode^%^22^%^3A^%^22zh-CN^%^22^%^2C^%^22lastConsentTimestamp^%^22^%^3A^%^222026-07-22T01^%^3A39^%^3A59.588Z^%^22^%^2C^%^22expirationTime^%^22^%^3A1800409199588^%^7D; _uetsid=403e0e20856e11f1825a636a6c107baf; _uetvid=403e1b30856e11f1bfb7b7610ed7fb79; _gcl_au=1.1.1947226011.1784684400; _ga=GA1.1.1971527756.1784684289; _clck=1eugybj^%^5E2^%^5Eg7y^%^5E1^%^5E2394; _clsk=4ng0up^%^5E1784684399614^%^5E1^%^5E1^%^5Ep.clarity.ms^%^2Fcollect; _ga_JKQYQYYR96=GS2.1.s1784684288^$o1^$g1^$t1784684405^$j54^$l0^$h2072316649; ttcsid_D756OKJC77UCP36TARSG=1784684286626::_eBI8XSZQeYETzlp4fxW.1.1784684412765.1; ttcsid=1784684286627::ICNFIGW5KBf1D809Bihv.1.1784684412765.0::1.126086.2961::126061.19.1733.287::109507.9.0'

COOKIE=$(printf '%s' "$RAWCOOKIE" | sed 's/\^//g')

URL="https://app.pea.ai/creator/profile/08345332-8a9d-4206-b51d-93510f38fe80"

echo "=== Fetching PAGE HTML ==="
curl -s "$URL" \
  -H "authorization: Bearer $JWT" \
  -H "accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
  -H "accept-language: zh-CN,zh;q=0.9" \
  -H "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36" \
  -H "referer: $URL" \
  -b "$COOKIE" \
  -o page_profile.html -w "HTTP %{http_code} size=%{size_download}\n"

echo "=== Fetching PROFILE API (JSON) ==="
curl -s "https://app.pea.ai/api/community/creator/08345332-8a9d-4206-b51d-93510f38fe80/profile" \
  -H "accept: */*" \
  -H "authorization: Bearer $JWT" \
  -H "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36" \
  -b "$COOKIE" \
  -o page_api.json -w "HTTP %{http_code} size=%{size_download}\n"

echo "=== Quick scan of page HTML ==="
grep -o '账户管理' page_profile.html | head -1 || echo "no 账户管理 literal in HTML"
grep -oE 'src="[^"]+\.js"' page_profile.html | head -20 || echo "no js src found"
grep -oE '<title>[^<]+</title>' page_profile.html | head -1
