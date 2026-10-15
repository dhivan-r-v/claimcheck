"""Source of truth for the evaluation set. Run to regenerate eval/dataset.jsonl.

Labels
  SCAM      scam, phishing or a false claim. The patterns are modelled on real forwards that PIB
            Fact Check and Indian fact-checkers have debunked. Links and phone numbers are made up.
  VERIFIED  genuine public information that an official (.gov.in / regulator) source confirms.
"""
import json
from pathlib import Path

S, V = "SCAM", "VERIFIED"

ITEMS = [
    # ---------------- scams / false claims ----------------
    ("s01", S, "hinglish", "fake_scheme",
     "PM Kisan Yojana ki 21vi kist mein sabhi kisano ko 6000 ki jagah 12000 milenge! Abhi register karo: "
     "pmkisan-gov.in.apply-now.xyz/reg  Last date aaj hi hai, jaldi karo aur 10 groups mein forward karo"),
    ("s02", S, "tamil", "utility_threat",
     "அன்புள்ள மின் நுகர்வோரே, உங்கள் கடந்த மாத மின் கட்டணம் செலுத்தப்படவில்லை. இன்றிரவு 9.30 மணிக்கு உங்கள் "
     "மின் இணைப்பு துண்டிக்கப்படும். உடனே எங்கள் அதிகாரியை அழைக்கவும் 9876543210"),
    ("s03", S, "hindi", "bank_phishing",
     "प्रिय ग्राहक, आपका SBI YONO खाता आज बंद हो जाएगा। तुरंत अपना PAN कार्ड अपडेट करें: sbi-yono-kyc.in/update "
     "नहीं तो खाता ब्लॉक हो जाएगा।"),
    ("s04", S, "english", "tax_refund", "", "samples/itr-refund-scam.png"),
    ("s05", S, "english", "utility_threat",
     "Dear Consumer, your electricity power will be disconnected tonight at 9:30 PM because your previous month "
     "bill was not updated. Please immediately contact our electricity officer 9876501234. Thank you."),
    ("s06", S, "english", "prize_lottery",
     "Congratulations! Your mobile number has won Rs 25,00,000 in the KBC Jio Lucky Draw 2026. To claim your prize "
     "contact our manager on WhatsApp +92 300 1234567 and pay the processing fee of Rs 12,500."),
    ("s07", S, "english", "fake_scheme",
     "PM Modi is giving a FREE 3-month recharge of Rs 719 to all Indian users to celebrate Digital India! "
     "Click here to get yours before the offer ends: free-recharge-modi.top/claim"),
    ("s08", S, "english", "delivery_phishing",
     "India Post: Your package is held at our warehouse due to an incomplete address. Update your address "
     "within 12 hours or it will be returned: indiapost-redelivery.xyz/in"),
    ("s09", S, "english", "bank_phishing",
     "Dear user, your PAN card will be blocked today as your KYC is not updated. Update now: http://bit.ly/pan-kyc-upd8"),
    ("s10", S, "english", "job_scam",
     "Part time job! Earn Rs 5000-8000 daily from home just by liking YouTube videos. No experience needed. "
     "Message HR Priya on WhatsApp 9123456780. Registration fee only Rs 499."),
    ("s11", S, "english", "impersonation",
     "This is a call from TRAI. Your mobile number will be disconnected in 2 hours because it was used in illegal "
     "activities. Press 9 to speak to our officer immediately."),
    ("s12", S, "hindi", "fake_scheme",
     "प्रधानमंत्री बेरोजगारी भत्ता योजना 2026 के तहत सभी बेरोजगार युवाओं को हर महीने ₹3500 मिलेंगे। "
     "अभी फॉर्म भरें: pm-berojgari-bhatta.in"),
    ("s13", S, "english", "fake_scheme",
     "Government will give free laptops to all students under PM Free Laptop Yojana 2026. Apply now with your "
     "Aadhaar: pmlaptopyojana.online"),
    ("s14", S, "english", "misinformation",
     "BREAKING: RBI has announced that all Rs 500 notes will become invalid from next month. Deposit all your "
     "Rs 500 notes in the bank before the 31st. Forward to everyone!"),
    ("s15", S, "english", "misinformation",
     "New WhatsApp and phone call rules from tomorrow: all calls will be recorded, all social media accounts will be "
     "monitored by the government, and anyone sending a political message will be arrested without warrant."),
    ("s16", S, "tanglish", "bank_phishing",
     "Ungal SBI reward points 7,250 inniku expire aaga pogudhu. Udane redeem pannunga, indha app download "
     "pannunga: SBI-Rewardz.apk"),
    ("s17", S, "english", "kyc_phishing",
     "Your FASTag KYC is incomplete and your FASTag will be blacklisted today. Update immediately: "
     "fastag-kyc-update.click"),
    ("s18", S, "hinglish", "family_emergency",
     "Mummy ka accident ho gaya hai, main hospital mein hu. Urgent 20000 GPay karo is number pe 9988776655, "
     "mera phone kharab hai, call mat karna"),
    ("s19", S, "english", "health_misinformation",
     "Ministry of Health advisory: drinking hot water with lemon every morning kills cancer cells. Doctors are "
     "hiding this. Forward to all your groups!"),
    ("s20", S, "english", "fake_scheme",
     "Get 50% off your electricity bill under PM Bijli Bill Mafi Yojana. Register with your Aadhaar and bank details "
     "today: bijli-bill-mafi.in"),
    ("s21", S, "hindi", "digital_arrest",
     "आपके नाम पर भेजे गए कूरियर में ड्रग्स मिले हैं। मुंबई पुलिस और CBI से बात करने के लिए 1 दबाएं, "
     "नहीं तो 2 घंटे में आपकी गिरफ्तारी होगी।"),
    ("s22", S, "tamil", "fake_scheme",
     "தமிழக அரசு அனைத்து கல்லூரி மாணவிகளுக்கும் இலவச ஸ்கூட்டி வழங்குகிறது. இன்றே பதிவு செய்யுங்கள்: tn-free-scooty.in"),
    ("s23", S, "english", "fake_scheme",
     "All Aadhaar card holders will get Rs 4,000 under the PM Aadhaar Card Yojana. Click here to claim: "
     "aadhaar-yojana-4000.xyz"),
    ("s24", S, "english", "pf_phishing",
     "EPFO update: you can now withdraw your full PF amount instantly. Just share your UAN number and the OTP you "
     "receive with our agent on 9012345678."),
    # ---------------- zero-day scams ----------------
    # Invented schemes, apps and offers that do not exist anywhere, so there is no search history,
    # fact-check or news about them. Only the manipulation playbook can give them away.
    ("z01", S, "english", "zero_day",
     "Ministry of Digital Welfare: Under the new Bharat Digital Suraksha Bonus 2026, every smartphone user is "
     "entitled to Rs 6,250. Verify your identity within 3 hours by sending your Aadhaar number and the OTP you "
     "receive to our verification officer on WhatsApp 9812300456."),
    ("z02", S, "hinglish", "zero_day",
     "Namaste! Rashtriya Kisan Samriddhi Card 2026 launch ho gaya hai. Har kisan ko 18,000 seedha account mein. "
     "Card activate karne ke liye 199 processing fee is UPI ID pe bhejo: ksamriddhi@ybl. Kal tak hi valid hai. "
     "Kisi ko mat batana, limited seats."),
    ("z03", S, "hindi", "zero_day",
     "महिला शक्ति डिजिटल सम्मान योजना: सभी महिलाओं को ₹11,000 का डिजिटल सम्मान मिलेगा। अभी रजिस्टर करें, केवल "
     "आज रात 12 बजे तक। अपना बैंक खाता नंबर और ATM पिन इस नंबर पर भेजें: 9001234567"),
    ("z04", S, "tamil", "zero_day",
     "தமிழ்நாடு டிஜிட்டல் இளைஞர் உதவித் திட்டம்: 18-30 வயதுடைய அனைவருக்கும் ₹15,000. இன்று இரவுக்குள் இந்த "
     "செயலியை பதிவிறக்கம் செய்து பதிவு செய்யுங்கள்: TN-Youth-Help.apk. யாரிடமும் சொல்ல வேண்டாம்."),
    ("z05", S, "english", "zero_day",
     "This is Inspector Sharma from the Cyber Crime Cell. A SIM card registered on your Aadhaar was used for money "
     "laundering. Do not disconnect this call or tell your family. Transfer your savings to the RBI safe-custody "
     "account we provide to clear your name."),
    ("z06", S, "tanglish", "zero_day",
     "Ungalukku Jio 5G Loyalty Reward 4,999 kidaichirukku! 30 nimishathukkulla claim pannunga: jio-loyalty5g.shop. "
     "Inga ungal debit card number matrum CVV podunga."),
    ("z07", S, "english", "zero_day",
     "Indian Railways Senior Citizen Travel Grant 2026: passengers above 55 get Rs 9,500 travel credit. Register at "
     "irctc-seniorgrant.site and pay the Rs 350 verification charge. Offer closes in 6 hours. Share in 5 groups to "
     "unlock a bonus."),
    ("z08", S, "hinglish", "zero_day",
     "Bhai, maine ek naya app join kiya - NiveshDouble. Isme 2000 invest karo, 7 din mein 6000 milta hai, government "
     "approved hai. Mere referral link se join karo: niveshdouble.top/ref/4471. Aaj ka offer hai bas."),
    # ---------------- genuine ----------------
    ("g01", V, "english", "scheme",
     "PM-KISAN: The 21st instalment of Rs 2,000 has been released to eligible farmers. Check your beneficiary "
     "status at https://pmkisan.gov.in"),
    ("g02", V, "english", "safety_advice",
     "RBI Kehta Hai: Never share your OTP, PIN, CVV or passwords with anyone, even if they claim to be calling from "
     "your bank or the RBI."),
    ("g03", V, "english", "safety_advice",
     "Been a victim of online fraud? Call the national cyber crime helpline 1930 or report it at "
     "https://cybercrime.gov.in"),
    ("g04", V, "english", "service",
     "The Sanchar Saathi portal (sancharsaathi.gov.in) lets you check how many mobile connections are registered in "
     "your name and block your phone if it is lost or stolen."),
    ("g05", V, "english", "scheme",
     "All senior citizens aged 70 and above are now eligible for free health cover of up to Rs 5 lakh per family per "
     "year under Ayushman Bharat PM-JAY, irrespective of income, through the Ayushman Vay Vandana card."),
    ("g06", V, "english", "scheme",
     "Under PM Surya Ghar Muft Bijli Yojana, households can get up to 300 units of free electricity every month by "
     "installing rooftop solar, with a subsidy of up to Rs 78,000. Apply at https://pmsuryaghar.gov.in"),
    ("g07", V, "english", "scheme",
     "PM Vishwakarma scheme: traditional artisans and craftspeople can get collateral-free loans of up to Rs 3 lakh "
     "at a concessional interest rate of 5%, along with skill training."),
    ("g08", V, "english", "service",
     "Unorganised workers can register for free on the e-Shram portal (eshram.gov.in) and get an e-Shram card with "
     "a Universal Account Number."),
    ("g09", V, "english", "service",
     "Documents issued through DigiLocker are legally valid and treated as equivalent to the original physical "
     "documents under the IT Act."),
    ("g10", V, "tamil", "scheme",
     "கலைஞர் மகளிர் உரிமைத் தொகை திட்டத்தின் கீழ் தகுதியான குடும்பத் தலைவிகளுக்கு மாதம் ₹1,000 வழங்கப்படுகிறது."),
    ("g11", V, "hindi", "scheme",
     "आयुष्मान भारत योजना के तहत पात्र परिवारों को हर साल ₹5 लाख तक का मुफ्त इलाज मिलता है। अपनी पात्रता "
     "beneficiary.nha.gov.in पर जांचें।"),
    ("g12", V, "english", "scheme",
     "Pradhan Mantri Ujjwala Yojana provides deposit-free LPG connections to adult women from poor households."),
    ("g13", V, "english", "service",
     "You can download your digital voter ID card (e-EPIC) from the Election Commission's portal "
     "https://voters.eci.gov.in"),
    ("g14", V, "hinglish", "service",
     "Sanchar Saathi portal pe Chakshu feature se aap suspicious fraud calls aur SMS report kar sakte ho."),
    ("g15", V, "english", "scheme",
     "The loan limit under Pradhan Mantri Mudra Yojana has been raised from Rs 10 lakh to Rs 20 lakh with the new "
     "Tarun Plus category."),
    # Genuine messages that mention OTPs and deadlines: the fingerprint must not flag them.
    ("g17", V, "english", "safety_advice",
     "UIDAI: You can update your Aadhaar documents online on the myAadhaar portal (myaadhaar.uidai.gov.in). "
     "Never share your Aadhaar OTP with anyone."),
    ("g18", V, "english", "service",
     "Indian voters can apply for a new voter ID card by filling Form 6 online on the Election Commission's portal "
     "voters.eci.gov.in."),
    ("g16", V, "english", "scheme",
     "Atal Pension Yojana gives a guaranteed monthly pension of Rs 1,000 to Rs 5,000 after the age of 60, "
     "depending on your contribution."),
]


def main():
    out = Path(__file__).with_name("dataset.jsonl")
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for item in ITEMS:
            id_, label, lang, category, text, *image = item
            row = {"id": id_, "expected": label, "lang": lang, "category": category, "text": text}
            if image:
                row["image"] = image[0]
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(ITEMS)} items to {out}")


if __name__ == "__main__":
    main()
