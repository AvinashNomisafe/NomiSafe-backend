from django.contrib import admin
from .models import Policy, PolicyCoverage, PolicyNominee, PolicyBenefit, PolicyExclusion, HealthInsuranceDetails, CoveredMember, ExtractedDocument

Policy = admin.site.register(Policy)
PolicyCoverage = admin.site.register(PolicyCoverage)
PolicyNominee = admin.site.register(PolicyNominee)
PolicyBenefit = admin.site.register(PolicyBenefit)
PolicyExclusion = admin.site.register(PolicyExclusion)
HealthInsuranceDetails = admin.site.register(HealthInsuranceDetails)
CoveredMember = admin.site.register(CoveredMember)
ExtractedDocument = admin.site.register(ExtractedDocument)      