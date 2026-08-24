from enum import Enum


class HIPAACategory(Enum):
    NAMES = "1_NAMES"
    GEOGRAPHY = "2_GEOGRAPHY"
    DATES_AGES = "3_DATES_AGES"
    PHONE = "4_PHONE"
    FAX = "5_FAX"
    EMAIL = "6_EMAIL"
    SSN = "7_SSN"
    MRN = "8_MRN"
    HEALTH_PLAN = "9_HEALTH_PLAN"
    ACCOUNT = "10_ACCOUNT"
    CERTIFICATE = "11_CERTIFICATE"
    VEHICLE = "12_VEHICLE"
    DEVICE = "13_DEVICE"
    URL = "14_URL"
    IP = "15_IP"
    BIOMETRIC = "16_BIOMETRIC"
    PHOTO = "17_PHOTO"
    OTHER_ID = "18_OTHER_ID"


PSEUDONYM_PREFIXES = {
    HIPAACategory.NAMES: "NAME",
    HIPAACategory.GEOGRAPHY: "LOCATION",
    HIPAACategory.DATES_AGES: "DATE",
    HIPAACategory.PHONE: "PHONE",
    HIPAACategory.FAX: "FAX",
    HIPAACategory.EMAIL: "EMAIL",
    HIPAACategory.SSN: "SSN",
    HIPAACategory.MRN: "MRN",
    HIPAACategory.HEALTH_PLAN: "HEALTH_PLAN",
    HIPAACategory.ACCOUNT: "ACCOUNT",
    HIPAACategory.CERTIFICATE: "CERTIFICATE",
    HIPAACategory.VEHICLE: "VEHICLE",
    HIPAACategory.DEVICE: "DEVICE",
    HIPAACategory.URL: "URL",
    HIPAACategory.IP: "IP",
    HIPAACategory.BIOMETRIC: "BIOMETRIC",
    HIPAACategory.PHOTO: "PHOTO",
    HIPAACategory.OTHER_ID: "ID",
}
