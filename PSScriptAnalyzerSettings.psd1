# PSScriptAnalyzer settings — strict defaults with rules unsuited to these
# scripts disabled. Used by `make check-ps`.
@{
    Severity     = @('Error', 'Warning')
    ExcludeRules = @(
        # These are user-facing CLI scripts (installer, dev runner) where
        # colored Write-Host output is the intended UX, not a diagnostic.
        'PSAvoidUsingWriteHost',
        # Internal helper functions; CmdletBinding/ShouldProcess ceremony and
        # strict verb/noun conventions add no value to non-module dev scripts.
        'PSUseShouldProcessForStateChangingFunctions',
        'PSUseApprovedVerbs',
        'PSUseSingularNouns'
    )
}
