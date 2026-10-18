// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "Messages/GameplayMessageProcessor.h"

#include "ElimChainProcessor.generated.h"

USTRUCT()
struct FPlayerElimChainInfo
{
	GENERATED_BODY()
};

// Tracks a chain of eliminations (X eliminations without more than Y seconds passing between each one)
UCLASS(Abstract)
class UElimChainProcessor : public UGameplayMessageProcessor
{
	GENERATED_BODY()

public:
	virtual void StartListening() override;

protected:
	UPROPERTY(EditDefaultsOnly)
	float ChainTimeLimit = 4.5f;

	// The event to rebroadcast when a user gets a chain of a certain length
	UPROPERTY(EditDefaultsOnly)
	TMap<int32, FGameplayTag> ElimChainTags;

	// Runtime behavior and state are intentionally absent from this benchmark starter.
};
