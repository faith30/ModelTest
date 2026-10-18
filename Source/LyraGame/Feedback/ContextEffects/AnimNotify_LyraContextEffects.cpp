// Copyright Epic Games, Inc. All Rights Reserved.

#include "AnimNotify_LyraContextEffects.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(AnimNotify_LyraContextEffects)

// MODEL_BENCHMARK_STUB: context-effects. Reflected contracts remain for existing assets.
UAnimNotify_LyraContextEffects::UAnimNotify_LyraContextEffects()
{
}

void UAnimNotify_LyraContextEffects::PostLoad()
{
	Super::PostLoad();
}

#if WITH_EDITOR
void UAnimNotify_LyraContextEffects::PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent)
{
	Super::PostEditChangeProperty(PropertyChangedEvent);
}
#endif

FString UAnimNotify_LyraContextEffects::GetNotifyName_Implementation() const
{
	return Super::GetNotifyName_Implementation();
}

void UAnimNotify_LyraContextEffects::Notify(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation,
	const FAnimNotifyEventReference& EventReference)
{
	Super::Notify(MeshComp, Animation, EventReference);
}

#if WITH_EDITOR
void UAnimNotify_LyraContextEffects::ValidateAssociatedAssets()
{
	Super::ValidateAssociatedAssets();
}

void UAnimNotify_LyraContextEffects::SetParameters(FGameplayTag EffectIn, FVector LocationOffsetIn, FRotator RotationOffsetIn,
	FLyraContextEffectAnimNotifyVFXSettings VFXPropertiesIn, FLyraContextEffectAnimNotifyAudioSettings AudioPropertiesIn,
	bool bAttachedIn, FName SocketNameIn, bool bPerformTraceIn, FLyraContextEffectAnimNotifyTraceSettings TracePropertiesIn)
{
}
#endif
