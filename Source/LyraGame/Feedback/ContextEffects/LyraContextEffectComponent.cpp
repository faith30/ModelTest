// Copyright Epic Games, Inc. All Rights Reserved.

#include "LyraContextEffectComponent.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(LyraContextEffectComponent)

// MODEL_BENCHMARK_STUB: context-effects. Reflected contracts remain for existing assets.
ULyraContextEffectComponent::ULyraContextEffectComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	bAutoActivate = true;
}

void ULyraContextEffectComponent::BeginPlay()
{
	Super::BeginPlay();
}

void ULyraContextEffectComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	Super::EndPlay(EndPlayReason);
}

void ULyraContextEffectComponent::AnimMotionEffect_Implementation(const FName Bone, const FGameplayTag MotionEffect, USceneComponent* StaticMeshComponent,
	const FVector LocationOffset, const FRotator RotationOffset, const UAnimSequenceBase* AnimationSequence,
	const bool bHitSuccess, const FHitResult HitResult, FGameplayTagContainer Contexts,
	FVector VFXScale, float AudioVolume, float AudioPitch)
{
}

void ULyraContextEffectComponent::UpdateEffectContexts(FGameplayTagContainer NewEffectContexts)
{
}

void ULyraContextEffectComponent::UpdateLibraries(TSet<TSoftObjectPtr<ULyraContextEffectsLibrary>> NewContextEffectsLibraries)
{
}
