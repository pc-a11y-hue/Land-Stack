/* UI translations. English is the source; any key missing in another language falls back to English.
   Hindi / Tamil / Telugu / Malayalam strings were drafted for the prototype and should be reviewed
   by native speakers (and the state departments' official terminology) before real use.
   State-specific RECORD terms (Patta/Chitta, Jamabandi, Thandaper…) and AREA UNITS come from the
   backend state adapters, not from this file. */
const LANGS = { en: 'English', hi: 'हिन्दी', ta: 'தமிழ்', te: 'తెలుగు', ml: 'മലയാളം' };

const I18N = {
  en: {
    tagline: 'Unified land governance', language: 'Language', login: 'Login', logout: 'Logout',
    citizen_login: 'Citizen Login', officer_login: 'Officer Login', username: 'Username', password: 'Password',
    otp: 'One-time password (OTP)', verify: 'Verify', continue: 'Continue', cancel: 'Cancel',
    tab_map: 'Map', tab_search: 'Search', tab_myland: 'My Land', tab_txn: 'My Transactions', tab_updates: 'Updates',
    tab_register: 'Register Land', tab_deeds: 'Sale Deeds', tab_requests: 'Record Updates',
    tab_risk: 'Risk & Anomalies', tab_satellite: 'Satellite', tab_reports: 'Reports', tab_audit: 'Audit Log',
    layers: 'Layers', layer_base: 'Base layer', layer_essential: 'Essential layers', layer_additional: 'Additional layers',
    boundaries: 'Parcel boundaries', zone_labels: 'Zone labels', color_by: 'Colour by', zoning: 'Zoning / land use',
    encumbrance_layer: 'Encumbrance', building_layer: 'Building permission', tax_ring: 'Property tax status',
    satellite_layer: 'Satellite watch', utility_layer: 'Utility gaps', legend: 'Legend', my_plots: 'My plots',
    owner: 'Owner', ulpin: 'ULPIN', survey_no: 'Survey number', area: 'Area', zone: 'Zone',
    record_of_rights: 'Record of Rights', ownership_history: 'Ownership history', registration: 'Registration',
    encumbrance: 'Encumbrance', tax: 'Property tax', utilities: 'Utilities', valuation: 'Guideline valuation',
    status: 'Status', privacy: 'Privacy', show_my_name: 'Show my name publicly', bank: 'Bank & loan',
    building: 'Building permission', land_use: 'Land use', past_owners: 'Past owners',
    search_ph: 'Owner name, ULPIN or survey number', no_results: 'No results', search: 'Search',
    select_plot: 'Select a plot on the map to see its details.', restricted: 'Restricted view',
    pending_mutation: 'Sale registered — the Revenue department has not yet updated the Record of Rights.',
    demo_accounts: 'Try a demo account', choose: '— choose —', demo_otp: 'Demo SMS',
    offline: 'You are offline — land records need a connection.', install: 'Install app'
  },
  hi: {
    tagline: 'एकीकृत भूमि शासन', language: 'भाषा', login: 'लॉगिन', logout: 'लॉगआउट',
    citizen_login: 'नागरिक लॉगिन', officer_login: 'अधिकारी लॉगिन', username: 'उपयोगकर्ता नाम', password: 'पासवर्ड',
    otp: 'वन-टाइम पासवर्ड (OTP)', verify: 'सत्यापित करें', continue: 'आगे बढ़ें', cancel: 'रद्द करें',
    tab_map: 'नक्शा', tab_search: 'खोजें', tab_myland: 'मेरी भूमि', tab_txn: 'मेरे लेन-देन', tab_updates: 'सूचनाएं',
    tab_register: 'भूमि पंजीकरण', tab_deeds: 'बिक्री विलेख', tab_requests: 'अभिलेख अद्यतन',
    tab_risk: 'जोखिम और विसंगतियां', tab_satellite: 'उपग्रह', tab_reports: 'रिपोर्ट', tab_audit: 'ऑडिट लॉग',
    layers: 'परतें', layer_base: 'आधार परत', layer_essential: 'आवश्यक परतें', layer_additional: 'अतिरिक्त परतें',
    boundaries: 'भूखंड सीमाएं', zone_labels: 'क्षेत्र लेबल', color_by: 'रंग आधार', zoning: 'भूमि उपयोग',
    encumbrance_layer: 'भार (बंधक)', building_layer: 'निर्माण अनुमति', tax_ring: 'संपत्ति कर स्थिति',
    satellite_layer: 'उपग्रह निगरानी', utility_layer: 'सुविधा कमी', legend: 'संकेत', my_plots: 'मेरे भूखंड',
    owner: 'मालिक', survey_no: 'सर्वे संख्या', area: 'क्षेत्रफल', zone: 'क्षेत्र',
    record_of_rights: 'अधिकार अभिलेख', ownership_history: 'स्वामित्व इतिहास', registration: 'पंजीकरण',
    encumbrance: 'भार (बंधक)', tax: 'संपत्ति कर', utilities: 'सुविधाएं', valuation: 'मार्गदर्शी मूल्य',
    status: 'स्थिति', privacy: 'गोपनीयता', show_my_name: 'मेरा नाम सार्वजनिक रूप से दिखाएं', bank: 'बैंक और ऋण',
    building: 'निर्माण अनुमति', land_use: 'भूमि उपयोग', past_owners: 'पूर्व मालिक',
    search_ph: 'मालिक का नाम, ULPIN या सर्वे संख्या', no_results: 'कोई परिणाम नहीं', search: 'खोजें',
    select_plot: 'विवरण देखने के लिए नक्शे पर कोई भूखंड चुनें।', restricted: 'सीमित जानकारी',
    pending_mutation: 'बिक्री पंजीकृत हो चुकी है — राजस्व विभाग ने अभी अधिकार अभिलेख अद्यतन नहीं किया है।',
    demo_accounts: 'डेमो खाता आज़माएं', choose: '— चुनें —', demo_otp: 'डेमो एसएमएस',
    offline: 'आप ऑफ़लाइन हैं — भूमि अभिलेखों के लिए इंटरनेट चाहिए।', install: 'ऐप इंस्टॉल करें'
  },
  ta: {
    tagline: 'ஒருங்கிணைந்த நில நிர்வாகம்', language: 'மொழி', login: 'உள்நுழை', logout: 'வெளியேறு',
    citizen_login: 'குடிமகன் உள்நுழைவு', officer_login: 'அதிகாரி உள்நுழைவு', username: 'பயனர் பெயர்', password: 'கடவுச்சொல்',
    otp: 'ஒருமுறை கடவுச்சொல் (OTP)', verify: 'சரிபார்', continue: 'தொடர்க', cancel: 'ரத்து செய்',
    tab_map: 'வரைபடம்', tab_search: 'தேடல்', tab_myland: 'என் நிலம்', tab_txn: 'என் பரிவர்த்தனைகள்', tab_updates: 'அறிவிப்புகள்',
    tab_register: 'நில பதிவு', tab_deeds: 'விற்பனை பத்திரங்கள்', tab_requests: 'பதிவு புதுப்பிப்புகள்',
    tab_risk: 'ஆபத்து & முரண்பாடுகள்', tab_satellite: 'செயற்கைக்கோள்', tab_reports: 'அறிக்கைகள்', tab_audit: 'தணிக்கைப் பதிவு',
    layers: 'அடுக்குகள்', layer_base: 'அடிப்படை அடுக்கு', layer_essential: 'அத்தியாவசிய அடுக்குகள்', layer_additional: 'கூடுதல் அடுக்குகள்',
    boundaries: 'நில எல்லைகள்', zone_labels: 'மண்டல குறியீடுகள்', color_by: 'வண்ணம்', zoning: 'நில பயன்பாடு',
    encumbrance_layer: 'வில்லங்கம்', building_layer: 'கட்டட அனுமதி', tax_ring: 'சொத்து வரி நிலை',
    satellite_layer: 'செயற்கைக்கோள் கண்காணிப்பு', utility_layer: 'வசதி இடைவெளிகள்', legend: 'குறிப்பு', my_plots: 'என் நிலங்கள்',
    owner: 'உரிமையாளர்', survey_no: 'சர்வே எண்', area: 'பரப்பளவு', zone: 'மண்டலம்',
    record_of_rights: 'உரிமைப் பதிவேடு', ownership_history: 'உரிமை வரலாறு', registration: 'பதிவு',
    encumbrance: 'வில்லங்கம்', tax: 'சொத்து வரி', utilities: 'வசதிகள்', valuation: 'வழிகாட்டி மதிப்பு',
    status: 'நிலை', privacy: 'தனியுரிமை', show_my_name: 'என் பெயரை பொதுவில் காட்டு', bank: 'வங்கி & கடன்',
    building: 'கட்டட அனுமதி', land_use: 'நில பயன்பாடு', past_owners: 'முந்தைய உரிமையாளர்கள்',
    search_ph: 'உரிமையாளர் பெயர், ULPIN அல்லது சர்வே எண்', no_results: 'முடிவுகள் இல்லை', search: 'தேடு',
    select_plot: 'விவரங்களைக் காண வரைபடத்தில் ஒரு நிலத்தைத் தேர்ந்தெடுக்கவும்.', restricted: 'வரையறுக்கப்பட்ட காட்சி',
    pending_mutation: 'விற்பனை பதிவாகிவிட்டது — வருவாய்த் துறை இன்னும் உரிமைப் பதிவேட்டைப் புதுப்பிக்கவில்லை.',
    demo_accounts: 'டெமோ கணக்கை முயலவும்', choose: '— தேர்வு செய் —', demo_otp: 'டெமோ எஸ்எம்எஸ்',
    offline: 'நீங்கள் ஆஃப்லைனில் உள்ளீர்கள் — நிலப் பதிவுகளுக்கு இணைய இணைப்பு தேவை.', install: 'செயலியை நிறுவு'
  },
  te: {
    tagline: 'ఏకీకృత భూ పరిపాలన', language: 'భాష', login: 'లాగిన్', logout: 'లాగౌట్',
    citizen_login: 'పౌర లాగిన్', officer_login: 'అధికారి లాగిన్', username: 'వినియోగదారు పేరు', password: 'పాస్‌వర్డ్',
    otp: 'వన్-టైమ్ పాస్‌వర్డ్ (OTP)', verify: 'ధృవీకరించు', continue: 'కొనసాగించు', cancel: 'రద్దు చేయి',
    tab_map: 'మ్యాప్', tab_search: 'శోధన', tab_myland: 'నా భూమి', tab_txn: 'నా లావాదేవీలు', tab_updates: 'నవీకరణలు',
    tab_register: 'భూమి నమోదు', tab_deeds: 'విక్రయ దస్తావేజులు', tab_requests: 'రికార్డు నవీకరణలు',
    tab_risk: 'ప్రమాదం & అసమానతలు', tab_satellite: 'ఉపగ్రహం', tab_reports: 'నివేదికలు', tab_audit: 'ఆడిట్ లాగ్',
    layers: 'పొరలు', layer_base: 'ప్రాథమిక పొర', layer_essential: 'ముఖ్యమైన పొరలు', layer_additional: 'అదనపు పొరలు',
    boundaries: 'ప్లాట్ సరిహద్దులు', zone_labels: 'జోన్ లేబుళ్లు', color_by: 'రంగు ఆధారం', zoning: 'భూ వినియోగం',
    encumbrance_layer: 'భారం', building_layer: 'నిర్మాణ అనుమతి', tax_ring: 'ఆస్తి పన్ను స్థితి',
    satellite_layer: 'ఉపగ్రహ పర్యవేక్షణ', utility_layer: 'సౌకర్యాల లోటు', legend: 'సూచిక', my_plots: 'నా ప్లాట్లు',
    owner: 'యజమాని', survey_no: 'సర్వే నంబర్', area: 'విస్తీర్ణం', zone: 'జోన్',
    record_of_rights: 'హక్కుల రికార్డు', ownership_history: 'యాజమాన్య చరిత్ర', registration: 'నమోదు',
    encumbrance: 'భారం', tax: 'ఆస్తి పన్ను', utilities: 'సౌకర్యాలు', valuation: 'మార్గదర్శక విలువ',
    status: 'స్థితి', privacy: 'గోప్యత', show_my_name: 'నా పేరును బహిరంగంగా చూపించు', bank: 'బ్యాంకు & రుణం',
    building: 'నిర్మాణ అనుమతి', land_use: 'భూ వినియోగం', past_owners: 'గత యజమానులు',
    search_ph: 'యజమాని పేరు, ULPIN లేదా సర్వే నంబర్', no_results: 'ఫలితాలు లేవు', search: 'శోధించు',
    select_plot: 'వివరాలు చూడడానికి మ్యాప్‌లో ఒక ప్లాట్‌ను ఎంచుకోండి.', restricted: 'పరిమిత వీక్షణ',
    pending_mutation: 'విక్రయం నమోదైంది — రెవెన్యూ శాఖ ఇంకా హక్కుల రికార్డును నవీకరించలేదు.',
    demo_accounts: 'డెమో ఖాతాను ప్రయత్నించండి', choose: '— ఎంచుకోండి —', demo_otp: 'డెమో ఎస్ఎంఎస్',
    offline: 'మీరు ఆఫ్‌లైన్‌లో ఉన్నారు — భూ రికార్డులకు ఇంటర్నెట్ అవసరం.', install: 'యాప్ ఇన్‌స్టాల్ చేయండి'
  },
  ml: {
    tagline: 'ഏകീകൃത ഭൂഭരണം', language: 'ഭാഷ', login: 'ലോഗിൻ', logout: 'ലോഗൗട്ട്',
    citizen_login: 'പൗര ലോഗിൻ', officer_login: 'ഉദ്യോഗസ്ഥ ലോഗിൻ', username: 'ഉപയോക്തൃനാമം', password: 'പാസ്‌വേഡ്',
    otp: 'ഒറ്റത്തവണ പാസ്‌വേഡ് (OTP)', verify: 'സ്ഥിരീകരിക്കുക', continue: 'തുടരുക', cancel: 'റദ്ദാക്കുക',
    tab_map: 'ഭൂപടം', tab_search: 'തിരയുക', tab_myland: 'എന്റെ ഭൂമി', tab_txn: 'എന്റെ ഇടപാടുകൾ', tab_updates: 'അറിയിപ്പുകൾ',
    tab_register: 'ഭൂമി രജിസ്ട്രേഷൻ', tab_deeds: 'വിൽപ്പന ആധാരങ്ങൾ', tab_requests: 'രേഖ പുതുക്കൽ',
    tab_risk: 'അപകടസാധ്യതയും വൈരുദ്ധ്യങ്ങളും', tab_satellite: 'ഉപഗ്രഹം', tab_reports: 'റിപ്പോർട്ടുകൾ', tab_audit: 'ഓഡിറ്റ് ലോഗ്',
    layers: 'ലെയറുകൾ', layer_base: 'അടിസ്ഥാന ലെയർ', layer_essential: 'അത്യാവശ്യ ലെയറുകൾ', layer_additional: 'അധിക ലെയറുകൾ',
    boundaries: 'പ്ലോട്ട് അതിരുകൾ', zone_labels: 'മേഖലാ ലേബലുകൾ', color_by: 'നിറം', zoning: 'ഭൂവിനിയോഗം',
    encumbrance_layer: 'ബാധ്യത', building_layer: 'നിർമ്മാണ അനുമതി', tax_ring: 'വസ്തു നികുതി നില',
    satellite_layer: 'ഉപഗ്രഹ നിരീക്ഷണം', utility_layer: 'സൗകര്യ വിടവുകൾ', legend: 'സൂചിക', my_plots: 'എന്റെ പ്ലോട്ടുകൾ',
    owner: 'ഉടമ', survey_no: 'സർവേ നമ്പർ', area: 'വിസ്തീർണ്ണം', zone: 'മേഖല',
    record_of_rights: 'അവകാശ രേഖ', ownership_history: 'ഉടമസ്ഥതാ ചരിത്രം', registration: 'രജിസ്ട്രേഷൻ',
    encumbrance: 'ബാധ്യത', tax: 'വസ്തു നികുതി', utilities: 'സൗകര്യങ്ങൾ', valuation: 'ന്യായവില',
    status: 'നില', privacy: 'സ്വകാര്യത', show_my_name: 'എന്റെ പേര് പരസ്യമായി കാണിക്കുക', bank: 'ബാങ്കും വായ്പയും',
    building: 'നിർമ്മാണ അനുമതി', land_use: 'ഭൂവിനിയോഗം', past_owners: 'മുൻ ഉടമകൾ',
    search_ph: 'ഉടമയുടെ പേര്, ULPIN അല്ലെങ്കിൽ സർവേ നമ്പർ', no_results: 'ഫലങ്ങളില്ല', search: 'തിരയുക',
    select_plot: 'വിവരങ്ങൾ കാണാൻ ഭൂപടത്തിൽ ഒരു പ്ലോട്ട് തിരഞ്ഞെടുക്കുക.', restricted: 'പരിമിത കാഴ്ച',
    pending_mutation: 'വിൽപ്പന രജിസ്റ്റർ ചെയ്തു — റവന്യൂ വകുപ്പ് ഇതുവരെ അവകാശ രേഖ പുതുക്കിയിട്ടില്ല.',
    demo_accounts: 'ഡെമോ അക്കൗണ്ട് പരീക്ഷിക്കുക', choose: '— തിരഞ്ഞെടുക്കുക —', demo_otp: 'ഡെമോ എസ്എംഎസ്',
    offline: 'നിങ്ങൾ ഓഫ്‌ലൈനാണ് — ഭൂരേഖകൾക്ക് ഇന്റർനെറ്റ് വേണം.', install: 'ആപ്പ് ഇൻസ്റ്റാൾ ചെയ്യുക'
  }
};

let LANG = 'en';
function t(key) { return (I18N[LANG] && I18N[LANG][key]) || I18N.en[key] || key; }
function setLang(code) {
  if (!I18N[code]) code = 'en';
  LANG = code;
  try { localStorage.setItem('landstack_lang', code); } catch (e) { /* storage may be blocked */ }
  document.documentElement.lang = code;
  applyI18n();
}
function initLang() {
  let saved = null;
  try { saved = localStorage.getItem('landstack_lang'); } catch (e) { /* ignore */ }
  LANG = I18N[saved] ? saved : 'en';
  document.documentElement.lang = LANG;
}
function applyI18n(root) {
  (root || document).querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  (root || document).querySelectorAll('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.dataset.i18nPh); });
}
