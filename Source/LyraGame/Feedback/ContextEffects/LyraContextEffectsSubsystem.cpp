// Copyright Epic Games, Inc. All Rights Reserved.

#include "LyraContextEffectsSubsystem.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(LyraContextEffectsSubsystem)

// MODEL_BENCHMARK_STUB: context-effects. Reflected contracts remain for existing assets.
void ULyraContextEffectsSubsystem::SpawnContextEffects(
	const AActor* SpawningActor
	, USceneComponent* AttachToComponent
	, const FName AttachPoint
	, const FVector LocationOffset
	, const FRotator RotationOffset
	, FGameplayTag Effect
	, FGameplayTagContainer Contexts
	, TArray<UAudioComponent*>& AudioOut
	, TArray<UNiagaraComponent*>& NiagaraOut
	, FVector VFXScale
	, float AudioVolume
	, float AudioPitch)
{
	AudioOut.Reset();
	NiagaraOut.Reset();
}

bool ULyraContextEffectsSubsystem::GetContextFromSurfaceType(TEnumAsByte<EPhysicalSurface> PhysicalSurface, FGameplayTag& Context)
{
	Context = FGameplayTag();
	return false;
}

void ULyraContextEffectsSubsystem::LoadAndAddContextEffectsLibraries(AActor* OwningActor,
	TSet<TSoftObjectPtr<ULyraContextEffectsLibrary>> ContextEffectsLibraries)
{
}

void ULyraContextEffectsSubsystem::UnloadAndRemoveContextEffectsLibraries(AActor* OwningActor)
{
}
