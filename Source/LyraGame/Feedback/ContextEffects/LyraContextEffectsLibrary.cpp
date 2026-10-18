// Copyright Epic Games, Inc. All Rights Reserved.

#include "Feedback/ContextEffects/LyraContextEffectsLibrary.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(LyraContextEffectsLibrary)

// MODEL_BENCHMARK_STUB: context-effects. Reflected contracts remain for existing assets.
void ULyraContextEffectsLibrary::GetEffects(const FGameplayTag Effect, const FGameplayTagContainer Context,
	TArray<USoundBase*>& Sounds, TArray<UNiagaraSystem*>& NiagaraSystems)
{
	Sounds.Reset();
	NiagaraSystems.Reset();
}

void ULyraContextEffectsLibrary::LoadEffects()
{
}

EContextEffectsLibraryLoadState ULyraContextEffectsLibrary::GetContextEffectsLibraryLoadState()
{
	return EContextEffectsLibraryLoadState::Unloaded;
}

void ULyraContextEffectsLibrary::LoadEffectsInternal()
{
}

void ULyraContextEffectsLibrary::LyraContextEffectLibraryLoadingComplete(TArray<ULyraActiveContextEffects*> LyraActiveContextEffects)
{
}
